<?php
/**
 * MegaDL — config/Config.php
 * PHP configuration manager with auto-detection and JSON persistence.
 */

declare(strict_types=1);

class Config {
    private static ?Config $instance = null;
    private array $data = [];
    private string $path;

    private const DEFAULTS = [
        'dl_folder'      => '',
        'def_quality'    => 'best',
        'merge_format'   => 'mp4',
        'sub_lang'       => 'en',
        'speed_limit'    => 0,
        'timeout'        => 30,
        'retries'        => 3,
        'frag_retries'   => 5,
        'concurrent_frag'=> 4,
        'max_parallel'   => 3,
        'proxy'          => '',
        'embed_thumb'    => true,
        'embed_meta'     => true,
        'embed_subs'     => false,
        'sponsorblock'   => false,
        'auto_retry'     => true,
        'auto_resume'    => true,
        'archive_mode'   => true,
        'verbose'        => false,
        'debug_mode'     => false,
        'custom_args'    => '',
    ];

    private function __construct() {
        $base       = dirname(__DIR__);
        $this->path = $base . '/config/settings.json';

        if (!is_dir(dirname($this->path))) {
            mkdir(dirname($this->path), 0755, true);
        }

        $this->data = self::DEFAULTS;

        if (file_exists($this->path)) {
            $saved = json_decode(file_get_contents($this->path), true) ?? [];
            $this->data = array_merge($this->data, $saved);
        }

        if (empty($this->data['dl_folder'])) {
            $this->data['dl_folder'] = $this->detectDownloadDir();
        }
    }

    public static function getInstance(): self {
        if (!self::$instance) self::$instance = new self();
        return self::$instance;
    }

    public function get(string $key, mixed $default = null): mixed {
        return $this->data[$key] ?? $default;
    }

    public function set(string $key, mixed $value): void {
        $this->data[$key] = $value;
    }

    public function update(array $data): void {
        $this->data = array_merge($this->data, $data);
    }

    public function all(): array {
        return $this->data;
    }

    public function save(): void {
        file_put_contents($this->path, json_encode($this->data, JSON_PRETTY_PRINT));
    }

    private function detectDownloadDir(): string {
        $candidates = [];

        // Android
        if (file_exists('/sdcard')) {
            $candidates[] = '/sdcard/Download/MegaDL';
            $candidates[] = '/sdcard/Download';
            $candidates[] = '/storage/emulated/0/Download/MegaDL';
        }

        // Linux / Mac
        $home = getenv('HOME') ?: '/tmp';
        $candidates[] = $home . '/Downloads/MegaDL';
        $candidates[] = $home . '/Downloads';

        // Windows
        $userProfile = getenv('USERPROFILE');
        if ($userProfile) {
            $candidates[] = $userProfile . '\\Downloads\\MegaDL';
            $candidates[] = $userProfile . '\\Downloads';
        }

        // XAMPP
        $candidates[] = 'C:/xampp/htdocs/MegaDL/downloads';

        // Relative
        $candidates[] = dirname(__DIR__) . '/downloads';

        foreach ($candidates as $dir) {
            if (!is_dir($dir)) @mkdir($dir, 0755, true);
            if (is_dir($dir) && is_writable($dir)) {
                return $dir;
            }
        }

        $fallback = sys_get_temp_dir() . '/megadl_downloads';
        @mkdir($fallback, 0755, true);
        return $fallback;
    }
}
