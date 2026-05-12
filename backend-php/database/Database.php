<?php
/**
 * MegaDL — database/Database.php
 * PHP SQLite3 database with all CRUD operations.
 */

declare(strict_types=1);

require_once __DIR__ . '/../utils/helpers.php';

class Database {
    private static ?Database $instance = null;
    private SQLite3 $db;

    private function __construct() {
        $dbDir = dirname(__DIR__) . '/database';
        if (!is_dir($dbDir)) mkdir($dbDir, 0755, true);

        $this->db = new SQLite3($dbDir . '/megadl.db');
        $this->db->enableExceptions(true);
        $this->db->exec("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;");
        $this->initialize();
    }

    public static function getInstance(): self {
        if (!self::$instance) self::$instance = new self();
        return self::$instance;
    }

    private function initialize(): void {
        $this->db->exec("
            CREATE TABLE IF NOT EXISTS jobs (
                id          TEXT PRIMARY KEY,
                url         TEXT NOT NULL,
                title       TEXT,
                thumbnail   TEXT,
                uploader    TEXT,
                duration    REAL,
                resolution  TEXT,
                state       TEXT NOT NULL DEFAULT 'queued',
                progress    REAL DEFAULT 0,
                speed       REAL DEFAULT 0,
                eta         REAL DEFAULT 0,
                total_bytes INTEGER DEFAULT 0,
                fragment    TEXT,
                error       TEXT,
                options     TEXT,
                output_path TEXT,
                pid         INTEGER,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS history (
                id          TEXT PRIMARY KEY,
                job_id      TEXT,
                url         TEXT NOT NULL,
                title       TEXT,
                thumbnail   TEXT,
                state       TEXT,
                output_path TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS archive (
                id         TEXT PRIMARY KEY,
                extractor  TEXT,
                title      TEXT,
                ts         TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS favorites (
                id         TEXT PRIMARY KEY,
                job_id     TEXT,
                url        TEXT,
                title      TEXT,
                thumbnail  TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS logs (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                level   TEXT NOT NULL DEFAULT 'info',
                message TEXT NOT NULL,
                job_id  TEXT,
                time    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_state   ON jobs(state);
            CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_logs_time    ON logs(time DESC);
        ");
    }

    // ── Jobs ─────────────────────────────────────────────────

    public function createJob(array $job): array {
        $now = now_iso();
        $stmt = $this->db->prepare("
            INSERT INTO jobs (id, url, title, thumbnail, uploader, duration, resolution,
                state, progress, options, created_at, updated_at)
            VALUES (:id, :url, :title, :thumbnail, :uploader, :duration, :resolution,
                :state, 0, :options, :created_at, :updated_at)
        ");
        $stmt->bindValue(':id',          $job['id']);
        $stmt->bindValue(':url',         $job['url']);
        $stmt->bindValue(':title',       $job['title'] ?? '');
        $stmt->bindValue(':thumbnail',   $job['thumbnail'] ?? '');
        $stmt->bindValue(':uploader',    $job['uploader'] ?? '');
        $stmt->bindValue(':duration',    $job['duration'] ?? 0,    SQLITE3_FLOAT);
        $stmt->bindValue(':resolution',  $job['resolution'] ?? '');
        $stmt->bindValue(':state',       $job['state'] ?? 'queued');
        $stmt->bindValue(':options',     json_encode($job['options'] ?? []));
        $stmt->bindValue(':created_at',  $now);
        $stmt->bindValue(':updated_at',  $now);
        $stmt->execute();
        return $this->getJob($job['id']);
    }

    public function getJob(string $id): ?array {
        $stmt = $this->db->prepare('SELECT * FROM jobs WHERE id = :id');
        $stmt->bindValue(':id', $id);
        $result = $stmt->execute();
        $row    = $result->fetchArray(SQLITE3_ASSOC);
        return $row ? $this->normalizeJob($row) : null;
    }

    public function getJobs(string $filter = 'all', string $sort = 'date_desc', string $q = ''): array {
        $where  = [];
        $params = [];

        if ($filter === 'done')  { $where[] = "state = 'done'";  }
        elseif ($filter === 'error')  { $where[] = "state = 'error'"; }
        elseif ($filter === 'video')  { $where[] = "resolution != ''"; }
        elseif ($filter !== 'all')    { $where[] = "state = :state"; $params[':state'] = $filter; }

        if ($q) {
            $where[] = "(title LIKE :q OR url LIKE :q)";
            $params[':q'] = "%$q%";
        }

        $orderMap = [
            'date_desc'  => 'created_at DESC',
            'date_asc'   => 'created_at ASC',
            'name_asc'   => 'title ASC',
            'size_desc'  => 'total_bytes DESC',
        ];
        $order = $orderMap[$sort] ?? 'created_at DESC';
        $whereSQL = $where ? 'WHERE ' . implode(' AND ', $where) : '';

        $stmt = $this->db->prepare("SELECT * FROM jobs $whereSQL ORDER BY $order LIMIT 200");
        foreach ($params as $k => $v) $stmt->bindValue($k, $v);

        $result = $stmt->execute();
        $rows   = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) {
            $rows[] = $this->normalizeJob($row);
        }
        return $rows;
    }

    public function getActiveJobs(): array {
        $result = $this->db->query("SELECT * FROM jobs WHERE state IN ('queued','fetching','running','paused')");
        $rows   = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) $rows[] = $this->normalizeJob($row);
        return $rows;
    }

    public function updateJob(string $id, array $fields): void {
        $fields['updated_at'] = now_iso();
        if (isset($fields['options'])) $fields['options'] = json_encode($fields['options']);
        $sets = implode(', ', array_map(fn($k) => "$k = :$k", array_keys($fields)));
        $stmt = $this->db->prepare("UPDATE jobs SET $sets WHERE id = :id");
        foreach ($fields as $k => $v) $stmt->bindValue(":$k", $v);
        $stmt->bindValue(':id', $id);
        $stmt->execute();
    }

    public function deleteJob(string $id): void {
        $stmt = $this->db->prepare('DELETE FROM jobs WHERE id = :id');
        $stmt->bindValue(':id', $id);
        $stmt->execute();
    }

    public function pauseAllJobs(): void  { $this->db->exec("UPDATE jobs SET state='paused' WHERE state IN ('running','queued','fetching')"); }
    public function resumeAllJobs(): void { $this->db->exec("UPDATE jobs SET state='queued' WHERE state='paused'"); }
    public function cancelAllJobs(): void { $this->db->exec("UPDATE jobs SET state='cancelled' WHERE state IN ('running','queued','fetching','paused')"); }

    private function normalizeJob(array $row): array {
        if (!empty($row['options'])) {
            $row['options'] = json_decode($row['options'], true) ?? [];
        }
        return $row;
    }

    // ── History ──────────────────────────────────────────────

    public function addHistory(array $job): void {
        $stmt = $this->db->prepare("
            INSERT OR REPLACE INTO history (id, job_id, url, title, thumbnail, state, output_path, created_at)
            VALUES (:id, :job_id, :url, :title, :thumbnail, :state, :output_path, :created_at)
        ");
        $stmt->bindValue(':id',          uuid());
        $stmt->bindValue(':job_id',      $job['id'] ?? '');
        $stmt->bindValue(':url',         $job['url'] ?? '');
        $stmt->bindValue(':title',       $job['title'] ?? '');
        $stmt->bindValue(':thumbnail',   $job['thumbnail'] ?? '');
        $stmt->bindValue(':state',       $job['state'] ?? '');
        $stmt->bindValue(':output_path', $job['output_path'] ?? '');
        $stmt->bindValue(':created_at',  now_iso());
        $stmt->execute();
    }

    public function getHistory(int $limit = 100): array {
        $result = $this->db->query("SELECT * FROM history ORDER BY created_at DESC LIMIT $limit");
        $rows   = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) $rows[] = $row;
        return $rows;
    }

    public function clearHistory(): void { $this->db->exec('DELETE FROM history'); }

    // ── Archive ──────────────────────────────────────────────

    public function addArchive(string $id, string $extractor = '', string $title = ''): void {
        $stmt = $this->db->prepare('INSERT OR IGNORE INTO archive (id, extractor, title, ts) VALUES (:id,:ext,:title,:ts)');
        $stmt->bindValue(':id', $id); $stmt->bindValue(':ext', $extractor);
        $stmt->bindValue(':title', $title); $stmt->bindValue(':ts', now_iso());
        $stmt->execute();
    }

    public function getArchive(): array {
        $result = $this->db->query('SELECT * FROM archive ORDER BY ts DESC');
        $rows   = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) $rows[] = $row;
        return $rows;
    }

    public function clearArchive(): void { $this->db->exec('DELETE FROM archive'); }

    // ── Favorites ────────────────────────────────────────────

    public function addFavorite(array $job): void {
        $stmt = $this->db->prepare('INSERT OR IGNORE INTO favorites (id,job_id,url,title,thumbnail,created_at) VALUES (:id,:job_id,:url,:title,:thumb,:ts)');
        $stmt->bindValue(':id', uuid()); $stmt->bindValue(':job_id', $job['id'] ?? '');
        $stmt->bindValue(':url', $job['url'] ?? ''); $stmt->bindValue(':title', $job['title'] ?? '');
        $stmt->bindValue(':thumb', $job['thumbnail'] ?? ''); $stmt->bindValue(':ts', now_iso());
        $stmt->execute();
    }

    public function removeFavorite(string $jobId): void {
        $stmt = $this->db->prepare('DELETE FROM favorites WHERE job_id = :id');
        $stmt->bindValue(':id', $jobId); $stmt->execute();
    }

    public function getFavorites(): array {
        $result = $this->db->query('SELECT * FROM favorites ORDER BY created_at DESC');
        $rows   = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) $rows[] = $row;
        return $rows;
    }

    // ── Logs ─────────────────────────────────────────────────

    public function addLog(string $message, string $level = 'info', string $jobId = ''): void {
        $stmt = $this->db->prepare('INSERT INTO logs (level,message,job_id,time) VALUES (:l,:m,:j,:t)');
        $stmt->bindValue(':l', $level); $stmt->bindValue(':m', $message);
        $stmt->bindValue(':j', $jobId); $stmt->bindValue(':t', now_time());
        $stmt->execute();
    }

    public function getLogs(?string $level = null, int $limit = 500, string $jobId = ''): array {
        $where = [];
        if ($level)  $where[] = "level = '$level'";
        if ($jobId)  $where[] = "job_id = '$jobId'";
        $whereSQL = $where ? 'WHERE ' . implode(' AND ', $where) : '';
        $result   = $this->db->query("SELECT * FROM logs $whereSQL ORDER BY time DESC LIMIT $limit");
        $rows     = [];
        while ($row = $result->fetchArray(SQLITE3_ASSOC)) $rows[] = $row;
        return array_reverse($rows);
    }

    public function clearLogs(): void { $this->db->exec('DELETE FROM logs'); }

    // ── Stats ────────────────────────────────────────────────

    public function getStats(): array {
        return [
            'total'       => (int)$this->db->querySingle('SELECT COUNT(*) FROM jobs'),
            'active'      => (int)$this->db->querySingle("SELECT COUNT(*) FROM jobs WHERE state IN ('running','queued','fetching')"),
            'done'        => (int)$this->db->querySingle("SELECT COUNT(*) FROM jobs WHERE state='done'"),
            'total_bytes' => (int)$this->db->querySingle("SELECT COALESCE(SUM(total_bytes),0) FROM jobs WHERE state='done'"),
        ];
    }
}
