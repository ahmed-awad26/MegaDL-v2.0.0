<?php
/**
 * MegaDL — api/handlers/download.php
 * Starts yt-dlp as a background process, tracks PID.
 */

declare(strict_types=1);

function handle_download(array $body, Database $db, Config $config): void {
    $url = sanitize_url($body['url'] ?? '');
    if (!$url) { api_error('Invalid URL'); return; }

    $jobId = uuid();
    $opts  = array_filter($body, fn($k) => $k !== 'url', ARRAY_FILTER_USE_KEY);

    $job = $db->createJob([
        'id'        => $jobId,
        'url'       => $url,
        'title'     => $opts['title']     ?? '',
        'thumbnail' => $opts['thumbnail'] ?? '',
        'uploader'  => $opts['uploader']  ?? '',
        'duration'  => $opts['duration']  ?? 0,
        'state'     => 'queued',
        'options'   => $opts,
    ]);

    // Start download in background
    start_background_download($jobId, $url, $opts, $db, $config);

    api_ok(['job' => $job, 'job_id' => $jobId]);
}

function handle_batch(array $body, Database $db, Config $config): void {
    $urls = $body['urls'] ?? [];
    if (!$urls) { api_error('No URLs provided'); return; }

    $opts = array_filter($body, fn($k) => $k !== 'urls', ARRAY_FILTER_USE_KEY);
    $jobs = [];

    foreach ($urls as $url) {
        $clean = sanitize_url((string)$url);
        if (!$clean) continue;

        $jobId = uuid();
        $job   = $db->createJob([
            'id'      => $jobId,
            'url'     => $clean,
            'state'   => 'queued',
            'options' => $opts,
        ]);
        $jobs[] = $job;
        start_background_download($jobId, $clean, $opts, $db, $config);
    }

    api_ok(['jobs' => $jobs, 'count' => count($jobs)]);
}

function start_background_download(
    string $jobId, string $url, array $opts,
    Database $db, Config $config
): void {
    $ytdlp    = find_binary('yt-dlp');
    if (!$ytdlp) {
        $db->updateJob($jobId, ['state' => 'error', 'error' => 'yt-dlp not found']);
        return;
    }

    $dlFolder = $config->get('dl_folder', sys_get_temp_dir());
    if (!is_dir($dlFolder)) mkdir($dlFolder, 0755, true);

    $logFile  = dirname(__DIR__, 2) . '/logs/job_' . $jobId . '.log';
    $cmd      = build_ytdlp_command($ytdlp, $url, $opts, $config, $dlFolder);

    // Update state to fetching
    $db->updateJob($jobId, ['state' => 'fetching']);
    $db->addLog("Starting download: $url", 'info', $jobId);

    // Launch as background process
    if (PHP_OS_FAMILY === 'Windows') {
        $pidFile = dirname(__DIR__, 2) . '/logs/pid_' . $jobId . '.pid';
        $wrapper = dirname(__DIR__, 2) . '/logs/job_' . $jobId . '.bat';
        $psFile  = dirname(__DIR__, 2) . '/logs/run_' . $jobId . '.ps1';
        file_put_contents($wrapper, "@echo off\r\n$cmd > " . escapeshellarg($logFile) . " 2>&1\r\n");
        $psContent = "\$p = Start-Process -NoNewWindow -PassThru -FilePath '$wrapper';\r\n"
                   . "\$p.Id | Out-File -Encoding ASCII '$pidFile'";
        file_put_contents($psFile, $psContent);
        shell_exec("powershell -NoProfile -ExecutionPolicy Bypass -File \"$psFile\"");
        $waited = 0;
        while (!file_exists($pidFile) && $waited < 20) { usleep(100000); $waited++; }
        $pid = file_exists($pidFile) ? (int)trim(file_get_contents($pidFile)) : 0;
        @unlink($psFile);
        @unlink($pidFile);
        if ($pid) {
            $db->updateJob($jobId, ['state' => 'running', 'pid' => $pid]);
            start_progress_watcher($jobId, $pid, $logFile, $db);
        }
    } else {
        $fullCmd = "$cmd > " . escapeshellarg($logFile) . " 2>&1 & echo \$!";
        $pid     = trim(shell_exec($fullCmd) ?? '');
        if ($pid) {
            $db->updateJob($jobId, ['state' => 'running', 'pid' => (int)$pid]);
            start_progress_watcher($jobId, (int)$pid, $logFile, $db);
        }
    }
}

function build_ytdlp_command(
    string $ytdlp, string $url, array $opts,
    Config $config, string $dlFolder
): string {
    $quality = $opts['quality'] ?? $config->get('def_quality', 'best');
    $parts   = [escapeshellcmd($ytdlp)];

    // Format
    if ($quality === 'mp3') {
        $parts[] = '-x --audio-format mp3 --audio-quality 0';
    } elseif ($quality === 'm4a') {
        $parts[] = '-x --audio-format m4a';
    } elseif ($quality === 'best') {
        $parts[] = '-f "bestvideo+bestaudio/best"';
    } else {
        $parts[] = "-f \"bestvideo[height<=$quality]+bestaudio/best[height<=$quality]/best\"";
    }

    // Merge format
    if (!in_array($quality, ['mp3','m4a'])) {
        $merge = $opts['merge_format'] ?? $config->get('merge_format', 'mp4');
        $parts[] = "--merge-output-format $merge";
    }

    // Concurrent fragments
    $frag = (int)($opts['concurrent_frag'] ?? $config->get('concurrent_frag', 4));
    if ($frag > 1) $parts[] = "--concurrent-fragments $frag";

    // Retries
    $parts[] = '--retries ' . (int)($opts['retries'] ?? $config->get('retries', 3));
    $parts[] = '--fragment-retries ' . (int)($opts['frag_retries'] ?? $config->get('frag_retries', 5));
    $parts[] = '--socket-timeout ' . (int)($opts['timeout'] ?? $config->get('timeout', 30));

    // Speed limit
    $speed = (int)($opts['speed_limit'] ?? $config->get('speed_limit', 0));
    if ($speed > 0) $parts[] = "--limit-rate {$speed}K";

    // Proxy
    $proxy = $opts['proxy'] ?? $config->get('proxy', '');
    if ($proxy) $parts[] = '--proxy ' . escapeshellarg($proxy);

    // Subtitles
    if (!empty($opts['embed_subs']) || $config->get('embed_subs', false)) {
        $lang = $opts['sub_lang'] ?? $config->get('sub_lang', 'en');
        $parts[] = "--embed-subs --sub-langs $lang";
    }

    // Thumbnail
    if (!empty($opts['embed_thumb']) || $config->get('embed_thumb', true)) {
        $parts[] = '--embed-thumbnail';
    }

    // Metadata
    if (!empty($opts['embed_meta']) || $config->get('embed_meta', true)) {
        $parts[] = '--add-metadata';
    }

    // SponsorBlock
    if (!empty($opts['sponsorblock']) || $config->get('sponsorblock', false)) {
        $parts[] = '--sponsorblock-mark all';
    }

    // Archive
    if (!empty($opts['archive_mode']) || $config->get('archive_mode', true)) {
        $archiveFile = escapeshellarg($dlFolder . '/.megadl_archive.txt');
        $parts[] = "--download-archive $archiveFile";
    }

    // Playlist mode
    $mode = $opts['mode'] ?? 'single';
    if ($mode === 'single') $parts[] = '--no-playlist';

    // Progress + newline
    $parts[] = '--newline --progress';

    // Verbose
    if (!empty($opts['verbose']) || $config->get('verbose', false)) {
        $parts[] = '--verbose';
    }

    // Custom args
    $custom = trim($opts['custom_args'] ?? $config->get('custom_args', ''));
    if ($custom) $parts[] = $custom;

    // Output template
    $parts[] = '-o ' . escapeshellarg($dlFolder . '/%(title)s.%(ext)s');

    // URL
    $parts[] = escapeshellarg($url);

    return implode(' ', $parts);
}

function start_progress_watcher(string $jobId, int $pid, string $logFile, Database $db): void {
    $script = dirname(__DIR__, 2) . '/jobs/watcher.php';
    if (!file_exists($script) || !find_binary('php')) return;

    if (PHP_OS_FAMILY === 'Windows') {
        // Use a VBScript helper to launch PHP watcher in background without a console window
        $vbsFile = dirname(__DIR__, 2) . '/logs/watcher_' . $jobId . '.vbs';
        $vbs = 'CreateObject("WScript.Shell").Run '
            . '"php ' . str_replace('"', '""', $script)
            . ' ' . str_replace('"', '""', $jobId)
            . ' ' . (int)$pid
            . ' ' . str_replace('"', '""', $logFile) . '", 0, False';
        file_put_contents($vbsFile, $vbs);
        shell_exec("wscript.exe //Nologo \"$vbsFile\"");
        @unlink($vbsFile);
    } else {
        $nullDev = PHP_OS_FAMILY === 'Windows' ? 'NUL' : '/dev/null';
        $cmd = 'php ' . escapeshellarg($script)
            . ' ' . escapeshellarg($jobId)
            . ' ' . (int)$pid
            . ' ' . escapeshellarg($logFile)
            . ' > ' . $nullDev . ' 2>&1 &';
        shell_exec($cmd);
    }
}
