<?php
/**
 * MegaDL — api/handlers/files.php
 * File browser: list, delete, rename, download.
 */
declare(strict_types=1);

function _base_dir(Config $config): string {
    return rtrim($config->get('dl_folder', sys_get_temp_dir()), '/\\');
}

function _safe_path(string $base, string $rel): ?string {
    $full = realpath($base . DIRECTORY_SEPARATOR . $rel);
    if ($full === false) {
        // Path may not exist yet — resolve manually
        $full = $base . DIRECTORY_SEPARATOR . $rel;
    }
    // Security: must start with base
    if (!str_starts_with(realpath($base) . DIRECTORY_SEPARATOR, realpath($base) . DIRECTORY_SEPARATOR)) {
        return null;
    }
    $rBase = realpath($base);
    $rFull = realpath(dirname($full));
    if ($rBase && $rFull && !str_starts_with($rFull, $rBase)) return null;
    return $full;
}

function handle_files_list(Config $config): void {
    $base    = _base_dir($config);
    $relPath = $_GET['path'] ?? '';

    // Guard traversal
    if (str_contains($relPath, '..')) { api_error('Invalid path'); return; }

    $target = $base . ($relPath ? DIRECTORY_SEPARATOR . $relPath : '');

    if (!is_dir($target)) { api_ok(['files' => []]); return; }

    $files = [];
    $items = @scandir($target);
    if (!$items) { api_ok(['files' => []]); return; }

    foreach ($items as $name) {
        if ($name === '.' || $name === '..') continue;
        if (str_starts_with($name, '.')) continue; // hide hidden files

        $full    = $target . DIRECTORY_SEPARATOR . $name;
        $relFull = $relPath ? $relPath . '/' . $name : $name;
        $isDir   = is_dir($full);

        $files[] = [
            'name'     => $name,
            'path'     => $relFull,
            'type'     => $isDir ? 'dir' : 'file',
            'size'     => $isDir ? 0 : (int)@filesize($full),
            'modified' => (int)@filemtime($full),
        ];
    }

    // Dirs first, then files
    usort($files, fn($a, $b) =>
        ($a['type'] === 'dir' ? 0 : 1) <=> ($b['type'] === 'dir' ? 0 : 1)
        ?: strcasecmp($a['name'], $b['name'])
    );

    api_ok(['files' => $files]);
}

function handle_file_delete(array $body, Config $config): void {
    $path = $body['path'] ?? '';
    if (!$path || str_contains($path, '..')) { api_error('Invalid path'); return; }

    $base   = _base_dir($config);
    $target = $base . DIRECTORY_SEPARATOR . $path;

    if (!file_exists($target)) { api_error('File not found', 404); return; }

    try {
        if (is_file($target)) {
            unlink($target);
        } else {
            _rmdir_recursive($target);
        }
        api_ok(['deleted' => $path]);
    } catch (Throwable $e) {
        api_error($e->getMessage(), 500);
    }
}

function handle_file_rename(array $body, Config $config): void {
    $oldPath = $body['path'] ?? '';
    $newName = trim($body['name'] ?? '');

    if (!$oldPath || !$newName) { api_error('path and name required'); return; }
    if (str_contains($oldPath, '..') || str_contains($newName, '/') || str_contains($newName, '\\')) {
        api_error('Invalid path or name');
        return;
    }

    $base   = _base_dir($config);
    $target = $base . DIRECTORY_SEPARATOR . $oldPath;

    if (!file_exists($target)) { api_error('File not found', 404); return; }

    $newTarget = dirname($target) . DIRECTORY_SEPARATOR . safe_filename($newName);
    if (rename($target, $newTarget)) {
        $newRel = ltrim(str_replace($base, '', $newTarget), '/\\');
        api_ok(['renamed' => $newRel]);
    } else {
        api_error('Rename failed', 500);
    }
}

function handle_file_download(string $filePath, Config $config): void {
    if (str_contains($filePath, '..')) { http_response_code(403); exit; }

    $base   = _base_dir($config);
    $target = $base . DIRECTORY_SEPARATOR . $filePath;

    if (!is_file($target)) { http_response_code(404); exit; }

    $mime = mime_content_type($target) ?: 'application/octet-stream';
    $name = basename($target);

    header('Content-Type: ' . $mime);
    header('Content-Disposition: attachment; filename="' . addslashes($name) . '"');
    header('Content-Length: ' . filesize($target));
    header('Cache-Control: no-cache');
    readfile($target);
    exit;
}

function _rmdir_recursive(string $dir): void {
    if (!is_dir($dir)) return;
    $items = scandir($dir);
    foreach ($items as $item) {
        if ($item === '.' || $item === '..') continue;
        $path = $dir . DIRECTORY_SEPARATOR . $item;
        is_dir($path) ? _rmdir_recursive($path) : unlink($path);
    }
    rmdir($dir);
}
