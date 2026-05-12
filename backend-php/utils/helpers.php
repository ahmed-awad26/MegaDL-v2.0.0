<?php
/**
 * MegaDL — utils/helpers.php
 * Shared PHP utility functions.
 */

declare(strict_types=1);

function api_ok(array $data = []): void {
    echo json_encode(array_merge(['ok' => true], $data));
}

function api_error(string $msg, int $code = 400): void {
    http_response_code($code);
    echo json_encode(['ok' => false, 'error' => $msg]);
}

function sanitize_url(string $url): ?string {
    $url = trim($url);
    if (!preg_match('#^https?://#i', $url)) return null;
    if (str_contains($url, '..'))            return null;
    $blocked = ['doubleclick.net','adnxs.com','propellerads.com','ouo.io','linkvertise.com'];
    foreach ($blocked as $d) {
        if (str_contains($url, $d)) return null;
    }
    return filter_var($url, FILTER_VALIDATE_URL) ?: null;
}

function safe_filename(string $name): string {
    return preg_replace('/[^a-zA-Z0-9._\-\s]/', '_', $name);
}

function format_bytes(int $bytes): string {
    $units = ['B','KB','MB','GB','TB'];
    $i = 0;
    while ($bytes >= 1024 && $i < 4) { $bytes /= 1024; $i++; }
    return round($bytes, 1) . ' ' . $units[$i];
}

function now_iso(): string {
    return (new DateTime('now', new DateTimeZone('UTC')))->format('Y-m-d\TH:i:s');
}

function now_time(): string {
    return date('H:i:s');
}

function uuid(): string {
    return sprintf('%04x%04x-%04x-%04x-%04x-%04x%04x%04x',
        mt_rand(0, 0xffff), mt_rand(0, 0xffff),
        mt_rand(0, 0xffff),
        mt_rand(0, 0x0fff) | 0x4000,
        mt_rand(0, 0x3fff) | 0x8000,
        mt_rand(0, 0xffff), mt_rand(0, 0xffff), mt_rand(0, 0xffff)
    );
}

function find_binary(string $name): ?string {
    $paths = explode(PATH_SEPARATOR, getenv('PATH') ?: '');
    $extras = [
        '/usr/local/bin', '/usr/bin', '/bin',
        getenv('HOME') . '/.local/bin',
        '/data/data/com.termux/files/usr/bin',
    ];
    foreach (array_merge($paths, $extras) as $dir) {
        $full = rtrim($dir, '/') . '/' . $name;
        if (is_executable($full)) return $full;
        if (PHP_OS_FAMILY === 'Windows' && is_executable($full . '.exe')) return $full . '.exe';
    }
    return null;
}

function get_binary_version(string $binary): ?string {
    $output = shell_exec(escapeshellcmd($binary) . ' --version 2>&1');
    return $output ? trim(explode("\n", $output)[0]) : null;
}

function process_alive(int $pid): bool {
    if (PHP_OS_FAMILY === 'Windows') {
        $output = shell_exec("tasklist /FI \"PID eq $pid\" 2>NUL");
        return str_contains($output ?? '', (string)$pid);
    }
    return file_exists("/proc/$pid") || posix_kill($pid, 0);
}

function get_exit_code(int $pid): int {
    return 0;
}
