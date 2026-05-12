<?php
/**
 * MegaDL — api/handlers/diagnostics.php
 * System diagnostics: checks all dependencies and environment.
 */
declare(strict_types=1);

function handle_diagnostics(Config $config): void {
    $dlFolder = $config->get('dl_folder', '.');
    $checks   = [];
    $log      = [];

    // PHP
    $checks['php'] = [
        'ok'      => true,
        'version' => phpversion(),
        'sapi'    => PHP_SAPI,
    ];
    $log[] = '[PHP] ✅ ' . phpversion();

    // yt-dlp
    $ytdlp = find_binary('yt-dlp');
    if ($ytdlp) {
        $ver = get_binary_version($ytdlp);
        $checks['ytdlp'] = ['ok' => true, 'available' => true, 'path' => $ytdlp, 'version' => $ver ?? 'unknown'];
        $log[] = "[YT-DLP] ✅ $ver";
    } else {
        $checks['ytdlp'] = ['ok' => false, 'available' => false, 'error' => 'Not found'];
        $log[] = '[YT-DLP] ❌ Not found — install: pip install yt-dlp';
    }

    // ffmpeg
    $ffmpeg = find_binary('ffmpeg');
    if ($ffmpeg) {
        $ver = get_ffmpeg_version($ffmpeg);
        $checks['ffmpeg'] = ['ok' => true, 'available' => true, 'path' => $ffmpeg, 'version' => $ver ?? 'unknown'];
        $log[] = "[FFMPEG] ✅ $ver";
    } else {
        $checks['ffmpeg'] = ['ok' => false, 'available' => false, 'error' => 'Not found'];
        $log[] = '[FFMPEG] ⚠️ Not found — merge/convert will fail';
    }

    // Python
    $python = find_binary('python3') ?? find_binary('python');
    if ($python) {
        $ver = trim((string)shell_exec(escapeshellcmd($python) . ' --version 2>&1'));
        $checks['python'] = ['ok' => true, 'available' => true, 'version' => $ver];
        $log[] = "[PYTHON] ✅ $ver";
    } else {
        $checks['python'] = ['ok' => false, 'available' => false];
        $log[] = '[PYTHON] ⚠️ Not found (PHP backend active)';
    }

    // Storage
    $free  = disk_free_space($dlFolder)  ?: 0;
    $total = disk_total_space($dlFolder) ?: 0;
    $checks['storage'] = [
        'ok'    => $free > 0,
        'free'  => (int)$free,
        'total' => (int)$total,
        'used'  => (int)($total - $free),
        'path'  => $dlFolder,
    ];
    $log[] = '[STORAGE] ' . ($free > 0 ? '✅ ' . format_bytes((int)$free) . ' free' : '❌ Cannot read storage');

    // Writable
    $testFile = $dlFolder . '/.megadl_write_test';
    $writable = @file_put_contents($testFile, 'test') !== false;
    if ($writable) @unlink($testFile);
    $checks['writable'] = ['ok' => $writable, 'writable' => $writable, 'path' => $dlFolder];
    $log[] = '[WRITABLE] ' . ($writable ? '✅ Write OK' : '❌ Not writable: ' . $dlFolder);

    // SQLite
    $checks['sqlite'] = ['ok' => extension_loaded('sqlite3'), 'version' => SQLite3::version()['versionString'] ?? 'unknown'];
    $log[] = '[SQLITE] ' . (extension_loaded('sqlite3') ? '✅ ' . (SQLite3::version()['versionString'] ?? '') : '❌ Not available');

    // Network
    $online = @fsockopen('8.8.8.8', 53, $errno, $errstr, 3) !== false;
    $checks['network'] = ['ok' => $online, 'online' => $online];
    $log[] = '[NETWORK] ' . ($online ? '✅ Online' : '❌ Offline');

    $allOk = count(array_filter($checks, fn($c) => !($c['ok'] ?? false))) === 0;

    api_ok([
        'checks'  => $checks,
        'all_ok'  => $allOk,
        'backend' => 'php',
        'log'     => implode("\n", $log),
    ]);
}

function get_ffmpeg_version(string $ffmpeg): ?string {
    $out = shell_exec(escapeshellcmd($ffmpeg) . ' -version 2>&1');
    if (!$out) return null;
    preg_match('/ffmpeg version ([\S]+)/', $out, $m);
    return $m[1] ?? 'unknown';
}
