<?php
/**
 * MegaDL — api/handlers/info.php
 * Video info extraction via yt-dlp.
 */

declare(strict_types=1);

function handle_info(array $body, Config $config): void {
    $url = sanitize_url($body['url'] ?? '');
    if (!$url) { api_error('Invalid or blocked URL'); return; }

    $ytdlp = find_binary('yt-dlp');
    if (!$ytdlp) { api_error('yt-dlp not found. Install it: pip install yt-dlp', 503); return; }

    $timeout = (int)($body['opts']['timeout'] ?? $config->get('timeout', 30));
    $cmd = escapeshellcmd($ytdlp)
        . ' --dump-json --no-playlist --no-download'
        . ' --socket-timeout ' . $timeout
        . ' ' . escapeshellarg($url)
        . ' 2>&1';

    $output = shell_exec($cmd);
    if (!$output) { api_error('No output from yt-dlp', 500); return; }

    // Find first JSON line
    $json = null;
    foreach (explode("\n", $output) as $line) {
        $line = trim($line);
        if (str_starts_with($line, '{')) {
            $json = json_decode($line, true);
            if ($json) break;
        }
    }

    if (!$json) {
        // Try to extract error from output
        $lines = array_filter(explode("\n", $output));
        $last  = end($lines);
        api_error('yt-dlp error: ' . ($last ?: 'Unknown error'), 500);
        return;
    }

    // Normalize
    $formats = [];
    foreach ($json['formats'] ?? [] as $f) {
        $formats[] = [
            'format_id'  => $f['format_id'] ?? '',
            'ext'        => $f['ext'] ?? '',
            'height'     => $f['height'] ?? null,
            'width'      => $f['width'] ?? null,
            'filesize'   => $f['filesize'] ?? $f['filesize_approx'] ?? null,
            'vcodec'     => $f['vcodec'] ?? '',
            'acodec'     => $f['acodec'] ?? '',
            'format_note'=> $f['format_note'] ?? '',
        ];
    }

    api_ok([
        'id'         => $json['id'] ?? '',
        'title'      => $json['title'] ?? 'Unknown',
        'thumbnail'  => $json['thumbnail'] ?? '',
        'uploader'   => $json['uploader'] ?? $json['channel'] ?? '',
        'duration'   => $json['duration'] ?? 0,
        'height'     => $json['height'] ?? null,
        'resolution' => $json['resolution'] ?? '',
        'filesize'   => $json['filesize'] ?? $json['filesize_approx'] ?? null,
        'view_count' => $json['view_count'] ?? null,
        'is_live'    => $json['is_live'] ?? false,
        'formats'    => $formats,
    ]);
}
