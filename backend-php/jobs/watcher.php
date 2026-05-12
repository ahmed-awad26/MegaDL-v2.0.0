<?php
/**
 * MegaDL — jobs/watcher.php
 * Monitors a running yt-dlp process log file and updates job progress in DB.
 * Called as: php watcher.php <job_id> <pid> <log_file>
 */

declare(strict_types=1);

if (PHP_SAPI !== 'cli') exit;

require_once dirname(__DIR__) . '/utils/helpers.php';
require_once dirname(__DIR__) . '/database/Database.php';

$jobId   = $argv[1] ?? '';
$pid     = (int)($argv[2] ?? 0);
$logFile = $argv[3] ?? '';

if (!$jobId || !$pid || !$logFile) exit(1);

$db = Database::getInstance();

// Wait for log file to appear
$waited = 0;
while (!file_exists($logFile) && $waited < 10) {
    sleep(1); $waited++;
}

$fp      = @fopen($logFile, 'r');
$timeout = 3600; // 1 hour max watch time
$start   = time();

while (time() - $start < $timeout) {
    // Check if process still alive
    if (!process_alive($pid)) break;

    if ($fp) {
        while (($line = fgets($fp)) !== false) {
            $line = trim($line);
            if (!$line) continue;

            $db->addLog($line, 'debug', $jobId);

            // Parse progress
            $progress = parse_progress_line($line);
            if ($progress) {
                $db->updateJob($jobId, [
                    'progress'    => $progress['percent'],
                    'speed'       => $progress['speed'],
                    'eta'         => $progress['eta'],
                    'total_bytes' => $progress['total_bytes'],
                    'state'       => 'running',
                ]);
            }
        }
    }
    usleep(500000); // 0.5s
}

if ($fp) fclose($fp);

// Final state
$job = $db->getJob($jobId);
if ($job && $job['state'] === 'running') {
    // Process ended — check exit code via log
    $exitCode = get_exit_code($pid);
    if ($exitCode === 0 || $job['progress'] >= 99) {
        $db->updateJob($jobId, ['state' => 'done', 'progress' => 100]);
        $db->addLog('Download completed', 'info', $jobId);
        $db->addHistory($db->getJob($jobId));
    } else {
        $db->updateJob($jobId, ['state' => 'error', 'error' => "Process exited with code $exitCode"]);
        $db->addLog("Download failed (exit $exitCode)", 'error', $jobId);
    }
}

function parse_progress_line(string $line): ?array {
    // [download]  45.6% of 123.45MiB at 1.23MiB/s ETA 01:23
    if (!preg_match(
        '/\[download\]\s+([\d.]+)%\s+of\s+([\d.]+)(\w+)\s+at\s+([\d.]+)(\w+\/s)(?:\s+ETA\s+([\d:]+))?/',
        $line, $m
    )) return null;

    return [
        'percent'     => (float)$m[1],
        'total_bytes' => parse_size_php((float)$m[2], $m[3]),
        'speed'       => parse_speed_php((float)$m[4], $m[5]),
        'eta'         => parse_eta_php($m[6] ?? ''),
    ];
}

function parse_size_php(float $val, string $unit): int {
    $unit = strtoupper($unit);
    $map  = ['B'=>1,'KB'=>1024,'MB'=>1048576,'GB'=>1073741824,'MIB'=>1048576,'GIB'=>1073741824];
    return (int)($val * ($map[$unit] ?? 1));
}

function parse_speed_php(float $val, string $unit): float {
    $base = strtoupper(explode('/', $unit)[0]);
    $map  = ['B'=>1,'KB'=>1024,'MB'=>1048576,'MIB'=>1048576];
    return $val * ($map[$base] ?? 1);
}

function parse_eta_php(string $eta): int {
    if (!$eta) return 0;
    $parts = array_map('intval', explode(':', $eta));
    return match(count($parts)) {
        2 => $parts[0]*60 + $parts[1],
        3 => $parts[0]*3600 + $parts[1]*60 + $parts[2],
        default => 0
    };
}
