import { useEffect, useMemo, useState, type ReactNode } from "react";

type ModuleKey = "settings" | "import" | "process" | "train" | "correct" | "pivot" | "tasks";
type Task = { task_id: string; task_name: string; task_type: string; status: string; progress: number; progress_text: string };
type TaskDetail = { parent: Task; sub_tasks: Task[] };
type ModelRecord = { task_id: string; model_name: string; element: string; model_path: string };
type LogItem = { id: string; title: string; detail: string; tone: "info" | "success" | "error" };
type TaskFilter = "ALL" | "PROCESSING" | "COMPLETED" | "FAILED" | "PENDING";
type StationOption = { name: string; raw: unknown };
type RawStationData = { station_name: string; lat: number; lon: number; timestamps: string[]; values: Array<number | null> };
type RawGridHeatmapData = { lats: number[]; lons: number[]; values: Array<Array<number | null>> };
type RawGridTimeseriesData = { lat: number; lon: number; timestamps: string[]; values: Array<number | null> };
type PivotProcessedData = { timestamps: string[]; station_values: Array<number | null>; grid_values: Array<number | null> };
type PivotHeatmapData = { lats: number[]; lons: number[]; values_before: Array<Array<number | null>>; values_after: Array<Array<number | null>> };
type PivotTimeseriesData = { timestamps: string[]; values_before: Array<number | null>; values_after: Array<number | null> };
type VisualKey = "raw-station" | "raw-grid" | "raw-grid-series" | "processed" | "compare-heatmap" | "compare-series";

const BASE_URL_KEY = "weather-correction-base-url";
const ELEMENTS = ["温度", "相对湿度", "过去1小时降水量", "2分钟平均风速"];
const SEASONS = ["全年", "春季", "夏季", "秋季", "冬季"];
const MODULES: Array<{ key: ModuleKey; title: string; desc: string }> = [
  { key: "settings", title: "数据源配置", desc: "维护站点、格点和基础资源路径" },
  { key: "import", title: "数据导入", desc: "检查文件并启动入库任务" },
  { key: "process", title: "数据预处理", desc: "按时间范围生成训练与分析底表" },
  { key: "train", title: "模型训练", desc: "配置训练集并发起模型训练" },
  { key: "correct", title: "数据订正", desc: "选择模型并执行格点订正" },
  { key: "pivot", title: "数据透视", desc: "分析站点对比并查看格点热力图" },
  { key: "tasks", title: "任务监控", desc: "查看父子任务状态与进度" },
];
const EMPTY_TASK: Task = { task_id: "", task_name: "", task_type: "", status: "IDLE", progress: 0, progress_text: "" };
const VISUAL_ORDER: VisualKey[] = ["raw-station", "raw-grid", "raw-grid-series", "processed", "compare-heatmap", "compare-series"];
const VISUAL_META: Record<VisualKey, { title: string; section: string; detail: string }> = {
  "raw-station": { title: "原始站点曲线", section: "原始预览", detail: "查看站点观测在所选时间范围内的变化节奏。" },
  "raw-grid": { title: "原始格点热力图", section: "原始预览", detail: "查看指定时刻的原始空间分布，并可直接选点。" },
  "raw-grid-series": { title: "原始格点时序", section: "原始预览", detail: "沿选中格点回看连续变化，判断原始数据稳定性。" },
  processed: { title: "站点对比分析", section: "订正对比", detail: "将站点实测与原始格点放到同一尺度下比对。" },
  "compare-heatmap": { title: "订正前后热力图", section: "订正对比", detail: "对照同一时刻订正前后的空间差异。" },
  "compare-series": { title: "订正前后时序", section: "订正对比", detail: "跟踪单个格点在订正前后的时序变化。" },
};

function clampProgress(value: unknown) {
  const n = Number(value ?? 0);
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

function mapTask(raw: Record<string, unknown>): Task {
  return {
    task_id: String(raw.task_id ?? ""),
    task_name: String(raw.task_name ?? "未命名任务"),
    task_type: String(raw.task_type ?? ""),
    status: String(raw.status ?? "UNKNOWN"),
    progress: clampProgress(raw.progress ?? raw.cur_progress),
    progress_text: String(raw.progress_text ?? raw.pregress_text ?? ""),
  };
}

function statusClass(status: string) {
  if (status === "COMPLETED") return "status-completed";
  if (status === "PROCESSING") return "status-processing";
  if (status === "FAILED") return "status-failed";
  if (status === "PENDING") return "status-pending";
  return "status-idle";
}

function statusLabel(status: string) {
  if (status === "COMPLETED") return "已完成";
  if (status === "PROCESSING") return "执行中";
  if (status === "FAILED") return "失败";
  if (status === "PENDING") return "等待中";
  if (status === "IDLE") return "未启动";
  return status || "未知";
}

function taskModule(taskType: string): ModuleKey {
  if (taskType.startsWith("DataImport")) return "import";
  if (taskType.startsWith("DataProcess")) return "process";
  if (taskType.startsWith("ModelTrain")) return "train";
  if (taskType.startsWith("DataCorrect")) return "correct";
  if (taskType.startsWith("Pivot")) return "pivot";
  return "tasks";
}

function parseStations(raw: unknown): StationOption[] {
  if (!raw || typeof raw !== "object" || !("station" in raw)) return [];
  const rows = (raw as { station?: unknown }).station;
  if (!Array.isArray(rows)) return [];
  return rows
    .map((item) => {
      if (Array.isArray(item) && item.length > 0) return { name: String(item[0] ?? ""), raw: item };
      if (item && typeof item === "object" && "name" in item) return { name: String((item as { name?: unknown }).name ?? ""), raw: item };
      return { name: String(item ?? ""), raw: item };
    })
    .filter((item) => item.name);
}

function toApiDateTime(value: string) {
  if (!value) return "";
  return value.length === 16 ? `${value}:00` : value;
}

function shiftHours(baseValue: string, hours: number) {
  const base = new Date(baseValue);
  if (Number.isNaN(base.getTime())) return { start: "", end: "" };
  const start = new Date(base.getTime() - hours * 60 * 60 * 1000);
  const pad = (value: number) => `${value}`.padStart(2, "0");
  const toLocalInput = (value: Date) => `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;
  return { start: toLocalInput(start), end: toLocalInput(base) };
}

function formatAxisTick(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${`${date.getMonth() + 1}`.padStart(2, "0")}-${`${date.getDate()}`.padStart(2, "0")} ${`${date.getHours()}`.padStart(2, "0")}:00`;
}

function formatMetric(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return "--";
  return value.toFixed(digits);
}

function average(values: Array<number | null | undefined>) {
  const valid = values.filter((item): item is number => typeof item === "number" && Number.isFinite(item));
  if (!valid.length) return null;
  return valid.reduce((sum, item) => sum + item, 0) / valid.length;
}

function diffAverage(a: Array<number | null | undefined>, b: Array<number | null | undefined>) {
  const pairs = a
    .map((item, index) => (typeof item === "number" && typeof b[index] === "number" ? item - (b[index] as number) : null))
    .filter((item): item is number => typeof item === "number" && Number.isFinite(item));
  if (!pairs.length) return null;
  return pairs.reduce((sum, item) => sum + item, 0) / pairs.length;
}

function flattenMatrix(values: Array<Array<number | null>>) {
  return values.flat().filter((item): item is number => typeof item === "number" && Number.isFinite(item));
}

function colorForValue(value: number | null, min: number, max: number) {
  if (value == null || !Number.isFinite(value)) return "rgba(255,255,255,0.08)";
  if (min === max) return "hsl(190 70% 55%)";
  const ratio = (value - min) / (max - min);
  const hue = 220 - ratio * 190;
  const light = 28 + ratio * 34;
  return `hsl(${hue} 78% ${light}%)`;
}

function buildLinePath(values: Array<number | null>, width: number, height: number) {
  const points = values
    .map((value, index) => ({ value, index }))
    .filter((item): item is { value: number; index: number } => typeof item.value === "number" && Number.isFinite(item.value));
  if (!points.length) return { path: "", min: 0, max: 0 };
  const min = Math.min(...points.map((item) => item.value));
  const max = Math.max(...points.map((item) => item.value));
  const range = max - min || 1;
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const path = points
    .map((point, idx) => {
      const x = point.index * step;
      const y = height - ((point.value - min) / range) * height;
      return `${idx === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
  return { path, min, max };
}

function Sparkline({ title, color, values }: { title: string; color: string; values: Array<number | null> }) {
  const { path, min, max } = useMemo(() => buildLinePath(values, 640, 180), [values]);

  return (
    <div className="chart-legend-item">
      <div className="chart-legend-top">
        <span className="chart-dot" style={{ background: color }} />
        <strong>{title}</strong>
      </div>
      <small>{formatMetric(min)} ~ {formatMetric(max)}</small>
      <svg viewBox="0 0 640 180" className="trend-mini">
        <path d={path} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" />
      </svg>
    </div>
  );
}

function MultiLineChart({ labels, series }: { labels: string[]; series: Array<{ name: string; color: string; values: Array<number | null> }> }) {
  const width = 680;
  const height = 220;
  const padding = 24;
  const valid = series.flatMap((item) => item.values.filter((value): value is number => typeof value === "number" && Number.isFinite(value)));
  const min = valid.length ? Math.min(...valid) : 0;
  const max = valid.length ? Math.max(...valid) : 1;
  const range = max - min || 1;
  const xStep = labels.length > 1 ? (width - padding * 2) / (labels.length - 1) : width - padding * 2;

  return (
    <div className="trend-card">
      <div className="trend-card-head">
        <div>
          <strong>趋势对比</strong>
          <small>站点实测、原始格点与订正结果可在同一尺度下对比</small>
        </div>
        <div className="chart-legend">
          {series.map((item) => (
            <span className="legend-item" key={item.name}>
              <i className="legend-dot" style={{ background: item.color }} />
              {item.name}
            </span>
          ))}
        </div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="trend-chart">
        {[0, 1, 2, 3].map((line) => {
          const y = padding + ((height - padding * 2) / 3) * line;
          return <line key={line} x1={padding} y1={y} x2={width - padding} y2={y} className="chart-grid-line" />;
        })}
        {series.map((item) => {
          const path = item.values
            .map((value, index) => {
              if (typeof value !== "number" || !Number.isFinite(value)) return null;
              const x = padding + index * xStep;
              const y = height - padding - ((value - min) / range) * (height - padding * 2);
              return `${x},${y}`;
            })
            .filter(Boolean)
            .join(" ");
          return <polyline key={item.name} points={path} fill="none" stroke={item.color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />;
        })}
        <text x={padding} y={18} className="chart-axis-label">{formatMetric(max)}</text>
        <text x={padding} y={height - 8} className="chart-axis-label">{formatMetric(min)}</text>
      </svg>
      <div className="chart-foot">
        <span>{labels[0] ? `起点 ${formatAxisTick(labels[0])}` : "暂无时间轴"}</span>
        <span>{labels.length ? `终点 ${formatAxisTick(labels[labels.length - 1])}` : ""}</span>
      </div>
    </div>
  );
}

function HeatmapMatrix({ title, values, lats, lons, focus, onSelect, subtitle }: {
  title: string;
  values: Array<Array<number | null>>;
  lats: number[];
  lons: number[];
  focus: { row: number; col: number } | null;
  onSelect: (row: number, col: number) => void;
  subtitle?: string;
}) {
  const allValues = useMemo(() => flattenMatrix(values), [values]);
  const min = allValues.length ? Math.min(...allValues) : 0;
  const max = allValues.length ? Math.max(...allValues) : 1;
  const rows = Math.max(values.length, 1);
  const cols = Math.max(lons.length, 1);
  const fittedWidth = Math.max(Math.min((320 * cols) / rows, 760), 220);

  return (
    <div className="heatmap-card">
      <div className="heatmap-head">
        <div>
          <strong>{title}</strong>
          {subtitle ? <small className="heatmap-subtitle">{subtitle}</small> : null}
        </div>
        <small>{formatMetric(min)} ~ {formatMetric(max)}</small>
      </div>
      <div
        className="heatmap-grid"
        style={{
          gridTemplateColumns: `repeat(${cols}, minmax(8px, 1fr))`,
          width: `min(100%, ${fittedWidth}px)`,
          marginInline: "auto",
        }}
      >
        {values.map((row, rowIndex) =>
          row.map((cell, colIndex) => {
            const selected = focus?.row === rowIndex && focus?.col === colIndex;
            return (
              <button
                key={`${rowIndex}-${colIndex}`}
                type="button"
                className={`heat-cell ${selected ? "selected" : ""}`}
                style={{ background: colorForValue(cell, min, max) }}
                title={`纬度 ${formatMetric(lats[rowIndex], 3)} / 经度 ${formatMetric(lons[colIndex], 3)} / 值 ${formatMetric(cell, 3)}`}
                onClick={() => onSelect(rowIndex, colIndex)}
              />
            );
          }),
        )}
      </div>
      <div className="heatmap-axis">
        <span>纬度 {lats.length ? `${formatMetric(lats[0], 2)} ~ ${formatMetric(lats[lats.length - 1], 2)}` : "--"}</span>
        <span>经度 {lons.length ? `${formatMetric(lons[0], 2)} ~ ${formatMetric(lons[lons.length - 1], 2)}` : "--"}</span>
      </div>
    </div>
  );
}

function VisualLaunchCard({
  title,
  detail,
  action,
  accent = "default",
}: {
  title: string;
  detail: string;
  action?: ReactNode;
  accent?: "default" | "good";
}) {
  return (
    <div className={`visual-launch-card ${accent === "good" ? "accent-good" : ""}`}>
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
      {action}
    </div>
  );
}

export default function App() {
  const [baseUrl, setBaseUrl] = useState(() => localStorage.getItem(BASE_URL_KEY) ?? "http://127.0.0.1:8000");
  const [moduleKey, setModuleKey] = useState<ModuleKey>("pivot");
  const [online, setOnline] = useState(false);
  const [busy, setBusy] = useState("");
  const [lastSync, setLastSync] = useState("--:--:--");
  const [settings, setSettings] = useState({ station_data_dir: "", grid_data_dir: "", station_info_path: "", dem_data_path: "" });
  const [importCount, setImportCount] = useState(0);
  const [importFiles, setImportFiles] = useState<string[]>([]);
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [stations, setStations] = useState<StationOption[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [taskFilter, setTaskFilter] = useState<TaskFilter>("ALL");
  const [taskSearch, setTaskSearch] = useState("");
  const [taskSort, setTaskSort] = useState<"progress_desc" | "progress_asc" | "name">("progress_desc");
  const [taskDetail, setTaskDetail] = useState<TaskDetail>({ parent: EMPTY_TASK, sub_tasks: [] });
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [processForm, setProcessForm] = useState({ elements: [...ELEMENTS], start_year: "2008", end_year: "2023", num_workers: "48" });
  const [trainForm, setTrainForm] = useState({ element: [...ELEMENTS], start_year: "2008", end_year: "2023", season: "全年", split_method: "按年份划分", test_set_values: "2022,2023", model: "XGBoost", early_stopping_rounds: "150" });
  const [correctForm, setCorrectForm] = useState({ model_path: "", element: "温度", start_year: "2008", end_year: "2023", season: "全年", block_size: "100", num_workers: "48" });
  const [pivotForm, setPivotForm] = useState({ station_name: "", element: "温度", start_time: "2023-01-01T00:00", end_time: "2023-01-03T00:00", heatmap_time: "2023-01-01T00:00", lat: "", lon: "" });
  const [rawStationData, setRawStationData] = useState<RawStationData | null>(null);
  const [rawGridData, setRawGridData] = useState<RawGridHeatmapData | null>(null);
  const [rawGridTaskId, setRawGridTaskId] = useState("");
  const [rawGridStatus, setRawGridStatus] = useState<{ status: string; progress: number; error?: string | null } | null>(null);
  const [rawGridSeriesData, setRawGridSeriesData] = useState<RawGridTimeseriesData | null>(null);
  const [visualKey, setVisualKey] = useState<VisualKey | null>(null);
  const [processedData, setProcessedData] = useState<PivotProcessedData | null>(null);
  const [heatmapData, setHeatmapData] = useState<PivotHeatmapData | null>(null);
  const [heatmapFocus, setHeatmapFocus] = useState<{ row: number; col: number } | null>(null);
  const [pivotSeriesTaskId, setPivotSeriesTaskId] = useState("");
  const [pivotSeriesStatus, setPivotSeriesStatus] = useState<{ status: string; progress: number; progress_text: string } | null>(null);
  const [pivotSeriesData, setPivotSeriesData] = useState<PivotTimeseriesData | null>(null);

  function addLog(title: string, detail: string, tone: LogItem["tone"]) {
    setLogs((current) => [{ id: `${Date.now()}-${Math.random()}`, title, detail, tone }, ...current].slice(0, 8));
  }

  async function api<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}${path}`, init);
    const text = await response.text();
    let data: unknown = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = text;
    }
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      if (typeof data === "string" && data) detail = data;
      if (typeof data === "object" && data && "detail" in data) {
        const value = (data as { detail?: unknown }).detail;
        detail = typeof value === "string" ? value : JSON.stringify(value);
      }
      throw new Error(detail);
    }
    return data as T;
  }

  async function refreshBase() {
    try {
      const [config, modelData, stationData] = await Promise.all([
        api<Record<string, unknown>>("/settings/all-config-info"),
        api<{ models?: ModelRecord[] }>("/data-correct/get-models"),
        api<unknown>("/data-preview/stations"),
      ]);
      setSettings({
        station_data_dir: String(config.station_data_dir ?? ""),
        grid_data_dir: String(config.grid_data_dir ?? ""),
        station_info_path: String(config.station_info_path ?? ""),
        dem_data_path: String(config.dem_data_path ?? ""),
      });
      const nextModels = modelData.models ?? [];
      setModels(nextModels);
      if (nextModels[0]) {
        setCorrectForm((current) => ({ ...current, model_path: current.model_path || nextModels[0].model_path, element: current.element || nextModels[0].element }));
      }
      const nextStations = parseStations(stationData);
      setStations(nextStations);
      if (nextStations[0]) {
        setPivotForm((current) => ({ ...current, station_name: current.station_name || nextStations[0].name }));
      }
      setOnline(true);
      setLastSync(new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }));
      localStorage.setItem(BASE_URL_KEY, baseUrl);
    } catch (error) {
      setOnline(false);
      addLog("连接失败", error instanceof Error ? error.message : "无法连接后端服务", "error");
    }
  }

  async function refreshTasks() {
    try {
      const history = await api<Array<Record<string, unknown>>>("/task_operate/history?limit=24");
      const next = history.map(mapTask);
      setTasks(next);
      if (!selectedTaskId && next[0]) setSelectedTaskId(next[0].task_id);
    } catch (error) {
      addLog("任务列表刷新失败", error instanceof Error ? error.message : "未知错误", "error");
    }
  }

  async function refreshTaskDetail(taskId: string) {
    if (!taskId) return;
    try {
      const detail = await api<{ parent: Record<string, unknown>; sub_tasks: Array<Record<string, unknown>> }>(`/task_operate/status/${encodeURIComponent(taskId)}/details`);
      setTaskDetail({ parent: mapTask(detail.parent), sub_tasks: (detail.sub_tasks ?? []).map(mapTask) });
    } catch {
      try {
        const parent = await api<Record<string, unknown>>(`/task_operate/status/${encodeURIComponent(taskId)}`);
        setTaskDetail({ parent: mapTask(parent), sub_tasks: [] });
      } catch (error) {
        addLog("任务详情刷新失败", error instanceof Error ? error.message : "未知错误", "error");
      }
    }
  }

  useEffect(() => {
    void refreshBase();
    void refreshTasks();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshBase();
      void refreshTasks();
    }, 6000);
    return () => window.clearInterval(timer);
  }, [baseUrl]);

  useEffect(() => {
    if (!selectedTaskId) return;
    void refreshTaskDetail(selectedTaskId);
    const timer = window.setInterval(() => void refreshTaskDetail(selectedTaskId), 3000);
    return () => window.clearInterval(timer);
  }, [selectedTaskId, baseUrl]);

  useEffect(() => {
    if (!pivotSeriesTaskId) return;
    let cancelled = false;
    const run = async () => {
      try {
        const result = await api<{ status: string; progress: number; progress_text: string; results?: PivotTimeseriesData | null }>(`/data-pivot/grid-data-timeseries/status/${pivotSeriesTaskId}`);
        if (cancelled) return;
        setPivotSeriesStatus({ status: result.status, progress: result.progress, progress_text: result.progress_text });
        if (result.status === "COMPLETED" && result.results) setPivotSeriesData(result.results);
      } catch (error) {
        if (cancelled) return;
        addLog("格点时序刷新失败", error instanceof Error ? error.message : "未知错误", "error");
      }
    };
    void run();
    const timer = window.setInterval(() => void run(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [pivotSeriesTaskId]);

  useEffect(() => {
    if (!rawGridTaskId) return;
    let cancelled = false;
    const run = async () => {
      try {
        const result = await api<{ status: string; progress: number; result?: RawGridTimeseriesData | null; error?: string | null }>(`/data-preview/grid-time-series/status/${rawGridTaskId}`);
        if (cancelled) return;
        setRawGridStatus({ status: result.status, progress: result.progress, error: result.error });
        if (result.status === "COMPLETED" && result.result) setRawGridSeriesData(result.result);
      } catch (error) {
        if (cancelled) return;
        addLog("原始格点时序刷新失败", error instanceof Error ? error.message : "未知错误", "error");
      }
    };
    void run();
    const timer = window.setInterval(() => void run(), 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [rawGridTaskId]);

  useEffect(() => {
    if (!visualKey) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setVisualKey(null);
        return;
      }
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      const available = VISUAL_ORDER.filter((key) => {
        if (key === "raw-station") return Boolean(rawStationData);
        if (key === "raw-grid") return Boolean(rawGridData);
        if (key === "raw-grid-series") return Boolean(rawGridSeriesData);
        if (key === "processed") return Boolean(processedData);
        if (key === "compare-heatmap") return Boolean(heatmapData);
        return Boolean(pivotSeriesData);
      });
      const currentIndex = available.indexOf(visualKey);
      if (currentIndex === -1 || available.length <= 1) return;
      const nextIndex = event.key === "ArrowRight"
        ? (currentIndex + 1) % available.length
        : (currentIndex - 1 + available.length) % available.length;
      setVisualKey(available[nextIndex]);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [visualKey, rawStationData, rawGridData, rawGridSeriesData, processedData, heatmapData, pivotSeriesData]);

  const stats = useMemo(() => ({
    processing: tasks.filter((item) => item.status === "PROCESSING").length,
    completed: tasks.filter((item) => item.status === "COMPLETED").length,
    failed: tasks.filter((item) => item.status === "FAILED").length,
  }), [tasks]);

  const filteredTasks = tasks
    .filter((item) => taskFilter === "ALL" || item.status === taskFilter)
    .filter((item) => {
      const q = taskSearch.trim().toLowerCase();
      if (!q) return true;
      return `${item.task_name} ${item.task_type} ${item.task_id}`.toLowerCase().includes(q);
    })
    .sort((a, b) => {
      if (taskSort === "progress_asc") return a.progress - b.progress;
      if (taskSort === "name") return a.task_name.localeCompare(b.task_name);
      return b.progress - a.progress;
    });

  const moduleTasks = filteredTasks.filter((item) => taskModule(item.task_type) === moduleKey).slice(0, 6);
  const taskHistoryView = moduleKey === "tasks" ? filteredTasks : tasks;
  const selectedModel = models.find((item) => item.model_path === correctForm.model_path) ?? models[0];

  const moduleHint = useMemo(() => {
    if (moduleKey === "settings") return "先确认四项基础路径，再进入导入、训练和订正流程。";
    if (moduleKey === "import") return "建议先检查文件数量与样本，再正式启动导入任务。";
    if (moduleKey === "process") return "先选时间范围和要素，再提交预处理任务。";
    if (moduleKey === "train") return "优先整理测试集配置，再发起训练。";
    if (moduleKey === "correct") return "确认模型和要素匹配后，再执行订正。";
    if (moduleKey === "pivot") return "训练前先看原始站点与原始格点，订正后再切到前后对比热力图和时序。";
    return "先按状态筛选，再查看右侧父任务和子任务的详细进度。";
  }, [moduleKey]);

  const moduleStage = useMemo(() => {
    if (moduleKey === "settings") return settings.station_data_dir && settings.grid_data_dir
      ? { label: "已配置", tone: "good", detail: "基础路径已经可用，可以继续业务流程。" }
      : { label: "待配置", tone: "warn", detail: "仍需补齐站点、格点等路径信息。" };
    if (moduleKey === "import") return importCount > 0
      ? { label: "可执行", tone: "good", detail: `已识别 ${importCount} 个待导入文件。` }
      : { label: "待检查", tone: "warn", detail: "建议先检查文件后再启动导入。" };
    if (moduleKey === "process") return processForm.elements.length > 0
      ? { label: "可执行", tone: "good", detail: `当前已选择 ${processForm.elements.length} 个要素。` }
      : { label: "待选择", tone: "warn", detail: "至少选择一个要素后再提交任务。" };
    if (moduleKey === "train") return trainForm.element.length > 0
      ? { label: "待训练", tone: "info", detail: `当前模型 ${trainForm.model}，可直接发起训练。` }
      : { label: "待选择", tone: "warn", detail: "请先选择训练要素。" };
    if (moduleKey === "correct") return selectedModel
      ? { label: "可订正", tone: "good", detail: `当前模型 ${selectedModel.model_name}` }
      : { label: "缺少模型", tone: "warn", detail: "需要先完成训练并生成模型记录。" };
    if (moduleKey === "pivot") return rawStationData || rawGridData || processedData || heatmapData
      ? { label: "已联动", tone: "good", detail: "原始预览和订正对比都已经可以分析。" }
      : { label: "待查询", tone: "info", detail: "选择时间与要素后即可生成透视结果。" };
    return { label: "监控中", tone: "info", detail: `当前筛选后共有 ${taskHistoryView.length} 条任务。` };
  }, [moduleKey, settings, importCount, processForm.elements.length, trainForm.element.length, trainForm.model, selectedModel, taskHistoryView.length, rawStationData, rawGridData, processedData, heatmapData]);

  const taskSummary = useMemo(() => {
    const subTasks = taskDetail.sub_tasks;
    return {
      total: subTasks.length,
      completed: subTasks.filter((item) => item.status === "COMPLETED").length,
      failed: subTasks.filter((item) => item.status === "FAILED").length,
      processing: subTasks.filter((item) => item.status === "PROCESSING").length,
    };
  }, [taskDetail.sub_tasks]);

  const processedSummary = useMemo(() => {
    if (!processedData) return null;
    return {
      stationMean: average(processedData.station_values),
      gridMean: average(processedData.grid_values),
      meanBias: diffAverage(processedData.station_values, processedData.grid_values),
      count: processedData.timestamps.length,
    };
  }, [processedData]);

  const rawSummary = useMemo(() => {
    if (!rawStationData) return null;
    return {
      stationMean: average(rawStationData.values),
      count: rawStationData.timestamps.length,
    };
  }, [rawStationData]);

  const focusMeta = useMemo(() => {
    if (!heatmapData || !heatmapFocus) return null;
    const { row, col } = heatmapFocus;
    return {
      lat: heatmapData.lats[row],
      lon: heatmapData.lons[col],
      before: heatmapData.values_before[row]?.[col] ?? null,
      after: heatmapData.values_after[row]?.[col] ?? null,
    };
  }, [heatmapData, heatmapFocus]);
  const rawFocusMeta = useMemo(() => {
    if (!rawGridData || !heatmapFocus) return null;
    const { row, col } = heatmapFocus;
    return {
      lat: rawGridData.lats[row],
      lon: rawGridData.lons[col],
      value: rawGridData.values[row]?.[col] ?? null,
    };
  }, [rawGridData, heatmapFocus]);

  async function runAction(key: string, work: () => Promise<void>) {
    try {
      setBusy(key);
      await work();
      await refreshTasks();
    } finally {
      setBusy("");
    }
  }

  function toggleList(target: string, kind: "process" | "train") {
    if (kind === "process") {
      setProcessForm((current) => ({ ...current, elements: current.elements.includes(target) ? current.elements.filter((item) => item !== target) : [...current.elements, target] }));
    } else {
      setTrainForm((current) => ({ ...current, element: current.element.includes(target) ? current.element.filter((item) => item !== target) : [...current.element, target] }));
    }
  }
  async function saveSettings() {
    await runAction("save-settings", async () => {
      await api("/settings/source-dirs", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      addLog("保存成功", "数据源路径已更新。", "success");
      await refreshBase();
    });
  }

  async function checkImportFiles() {
    await runAction("check-import", async () => {
      const result = await api<{ count: number; files: string[] }>("/data-import/check");
      setImportCount(result.count);
      setImportFiles(result.files ?? []);
      addLog("检查完成", `识别到 ${result.count} 个待导入文件。`, "success");
    });
  }

  async function startImport() {
    await runAction("start-import", async () => {
      const result = await api<{ task_id: string; message: string }>("/data-import/start", { method: "POST" });
      setSelectedTaskId(result.task_id);
      addLog("导入任务已启动", result.message, "success");
    });
  }

  async function startProcess() {
    await runAction("start-process", async () => {
      const result = await api<{ task_id: string; message: string }>("/data-process/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ elements: processForm.elements, start_year: processForm.start_year, end_year: processForm.end_year, num_workers: Number(processForm.num_workers) }),
      });
      setSelectedTaskId(result.task_id);
      addLog("预处理任务已启动", result.message, "success");
    });
  }

  async function startTrain() {
    await runAction("start-train", async () => {
      const result = await api<{ task_id: string; message: string }>("/model-train/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          element: trainForm.element,
          start_year: trainForm.start_year,
          end_year: trainForm.end_year,
          season: trainForm.season,
          split_method: trainForm.split_method,
          test_set_values: trainForm.test_set_values.split(/[,\n]/).map((item) => item.trim()).filter(Boolean),
          model: trainForm.model,
          early_stopping_rounds: trainForm.early_stopping_rounds,
        }),
      });
      setSelectedTaskId(result.task_id);
      addLog("训练任务已启动", result.message, "success");
    });
  }

  async function refreshModels() {
    await runAction("refresh-models", async () => {
      const result = await api<{ models?: ModelRecord[] }>("/data-correct/get-models");
      const next = result.models ?? [];
      setModels(next);
      if (next[0]) setCorrectForm((current) => ({ ...current, model_path: next[0].model_path, element: next[0].element }));
      addLog("模型列表已刷新", `当前可用模型 ${next.length} 个。`, "success");
    });
  }

  async function startCorrect() {
    await runAction("start-correct", async () => {
      const result = await api<{ task_id: string; message: string }>("/data-correct/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_path: correctForm.model_path,
          element: correctForm.element,
          start_year: correctForm.start_year,
          end_year: correctForm.end_year,
          season: correctForm.season,
          block_size: Number(correctForm.block_size),
          num_workers: Number(correctForm.num_workers),
        }),
      });
      setSelectedTaskId(result.task_id);
      addLog("订正任务已启动", result.message, "success");
    });
  }

  async function cancelTask() {
    if (!taskDetail.parent.task_id) return;
    await runAction("cancel-task", async () => {
      const result = await api<{ message: string }>(`/task_operate/${taskDetail.parent.task_id}/cancel`, { method: "POST" });
      addLog("取消请求已发送", result.message, "info");
      await refreshTaskDetail(taskDetail.parent.task_id);
    });
  }

  async function loadRawStationPreview(form = pivotForm) {
    await runAction("raw-station", async () => {
      const result = await api<RawStationData>("/data-preview/station-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          station_name: form.station_name,
          element: form.element,
          start_time: toApiDateTime(form.start_time),
          end_time: toApiDateTime(form.end_time),
        }),
      });
      setRawStationData(result);
      addLog("原始站点曲线已更新", `加载了 ${result.timestamps.length} 个时刻的站点观测值。`, "success");
    });
  }

  async function loadRawGridHeatmap(form = pivotForm) {
    await runAction("raw-grid-heatmap", async () => {
      const result = await api<RawGridHeatmapData>("/data-preview/grid-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ element: form.element, timestamp: toApiDateTime(form.heatmap_time) }),
      });
      setRawGridData(result);
      const row = Math.floor(result.lats.length / 2);
      const col = Math.floor(result.lons.length / 2);
      setPivotForm((current) => ({ ...current, lat: String(result.lats[row] ?? current.lat), lon: String(result.lons[col] ?? current.lon) }));
      addLog("原始格点热力图已更新", `已加载 ${result.lats.length} × ${result.lons.length} 的原始格点矩阵。`, "success");
    });
  }

  async function loadRawGridTimeseries(form = pivotForm) {
    await runAction("raw-grid-timeseries", async () => {
      const lat = Number(form.lat);
      const lon = Number(form.lon);
      if (Number.isNaN(lat) || Number.isNaN(lon)) throw new Error("请先提供有效的经纬度坐标。");
      const result = await api<{ task_id: string; message: string }>("/data-preview/grid-time-series", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          element: form.element,
          lat,
          lon,
          start_time: toApiDateTime(form.start_time),
          end_time: toApiDateTime(form.end_time),
        }),
      });
      setRawGridTaskId(result.task_id);
      setRawGridSeriesData(null);
      setRawGridStatus({ status: "PENDING", progress: 0, error: null });
      addLog("原始格点时序任务已启动", result.message, "success");
    });
  }

  async function loadProcessedPivot(form = pivotForm) {
    await runAction("pivot-processed", async () => {
      const result = await api<PivotProcessedData>("/data-pivot/processed-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ station_name: form.station_name, element: form.element, start_time: toApiDateTime(form.start_time), end_time: toApiDateTime(form.end_time) }),
      });
      setProcessedData(result);
      addLog("站点透视已更新", `加载了 ${result.timestamps.length} 个时刻的站点/格点对比数据。`, "success");
    });
  }

  async function loadHeatmap(form = pivotForm) {
    await runAction("pivot-heatmap", async () => {
      const result = await api<PivotHeatmapData>("/data-pivot/grid-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ element: form.element, timestamp: toApiDateTime(form.heatmap_time) }),
      });
      setHeatmapData(result);
      const nextFocus = { row: Math.floor(result.lats.length / 2), col: Math.floor(result.lons.length / 2) };
      setHeatmapFocus(nextFocus);
      setPivotForm((current) => ({ ...current, lat: String(result.lats[nextFocus.row] ?? ""), lon: String(result.lons[nextFocus.col] ?? "") }));
      addLog("热力图已更新", `已加载 ${result.lats.length} × ${result.lons.length} 的格点矩阵。`, "success");
    });
  }

  async function loadPivotTimeseries(form = pivotForm) {
    await runAction("pivot-timeseries", async () => {
      const lat = Number(form.lat);
      const lon = Number(form.lon);
      if (Number.isNaN(lat) || Number.isNaN(lon)) throw new Error("请先提供有效的经纬度坐标。");
      const result = await api<{ task_id: string; message: string }>("/data-pivot/grid-data-timeseries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ element: form.element, lat, lon, start_time: toApiDateTime(form.start_time), end_time: toApiDateTime(form.end_time) }),
      });
      setPivotSeriesTaskId(result.task_id);
      setPivotSeriesData(null);
      setPivotSeriesStatus({ status: "PENDING", progress: 0, progress_text: "任务已提交，等待执行..." });
      addLog("格点时序任务已启动", result.message, "success");
    });
  }

  async function applyQuickRange(hours: number) {
    const next = shiftHours(pivotForm.end_time, hours);
    if (!next.start || !next.end) return;
    const nextForm = { ...pivotForm, start_time: next.start, end_time: next.end };
    setPivotForm(nextForm);

    const jobs: Array<Promise<unknown>> = [];
    if (rawStationData) jobs.push(loadRawStationPreview(nextForm));
    if (rawGridStatus || rawGridSeriesData) jobs.push(loadRawGridTimeseries(nextForm));
    if (processedData) jobs.push(loadProcessedPivot(nextForm));
    if (pivotSeriesStatus || pivotSeriesData) jobs.push(loadPivotTimeseries(nextForm));

    if (jobs.length > 0) {
      await Promise.allSettled(jobs);
      addLog("快捷范围已应用", `时间范围已切换为最近 ${hours >= 24 ? `${hours / 24} 天` : `${hours} 小时`}，并自动刷新当前结果。`, "info");
    } else {
      addLog("快捷范围已应用", `时间范围已切换为最近 ${hours >= 24 ? `${hours / 24} 天` : `${hours} 小时`}。`, "info");
    }
  }

  function selectHeatCell(row: number, col: number) {
    setHeatmapFocus({ row, col });
    const source = heatmapData ? { lats: heatmapData.lats, lons: heatmapData.lons } : rawGridData ? { lats: rawGridData.lats, lons: rawGridData.lons } : null;
    if (!source) return;
    setPivotForm((current) => ({ ...current, lat: String(source.lats[row] ?? ""), lon: String(source.lons[col] ?? "") }));
  }

  const processedSeries = useMemo(() => {
    if (!processedData) return [];
    return [
      { name: "站点实测", color: "#7dc2ff", values: processedData.station_values },
      { name: "原始格点", color: "#ffd28a", values: processedData.grid_values },
    ];
  }, [processedData]);

  const rawStationSeries = useMemo(() => {
    if (!rawStationData) return [];
    return [{ name: "原始站点", color: "#7dc2ff", values: rawStationData.values }];
  }, [rawStationData]);

  const pivotTimeseriesSeries = useMemo(() => {
    if (!pivotSeriesData) return [];
    return [
      { name: "订正前", color: "#ff9c7a", values: pivotSeriesData.values_before },
      { name: "订正后", color: "#77efc7", values: pivotSeriesData.values_after },
    ];
  }, [pivotSeriesData]);

  const rawGridSeries = useMemo(() => {
    if (!rawGridSeriesData) return [];
    return [{ name: "原始格点", color: "#ffd28a", values: rawGridSeriesData.values }];
  }, [rawGridSeriesData]);

  const rawStatusItems = [
    { label: "站点曲线", active: Boolean(rawStationData), text: rawStationData ? "已就绪" : "未加载" },
    { label: "格点热力图", active: Boolean(rawGridData), text: rawGridData ? "已就绪" : "未加载" },
    { label: "格点时序", active: rawGridStatus?.status === "COMPLETED", text: rawGridStatus ? statusLabel(rawGridStatus.status) : "未启动" },
  ];

  const compareStatusItems = [
    { label: "站点对比", active: Boolean(processedData), text: processedData ? "已就绪" : "未加载" },
    { label: "前后热力图", active: Boolean(heatmapData), text: heatmapData ? "已就绪" : "未加载" },
    { label: "前后时序", active: pivotSeriesStatus?.status === "COMPLETED", text: pivotSeriesStatus ? statusLabel(pivotSeriesStatus.status) : "未启动" },
  ];
  const rangeLabel = `${formatAxisTick(toApiDateTime(pivotForm.start_time))} -> ${formatAxisTick(toApiDateTime(pivotForm.end_time))}`;
  const heatmapLabel = formatAxisTick(toApiDateTime(pivotForm.heatmap_time));
  const visualAvailability = useMemo<Record<VisualKey, boolean>>(() => ({
    "raw-station": Boolean(rawStationData),
    "raw-grid": Boolean(rawGridData),
    "raw-grid-series": Boolean(rawGridSeriesData),
    processed: Boolean(processedData),
    "compare-heatmap": Boolean(heatmapData),
    "compare-series": Boolean(pivotSeriesData),
  }), [rawStationData, rawGridData, rawGridSeriesData, processedData, heatmapData, pivotSeriesData]);
  const availableVisualKeys = useMemo(() => VISUAL_ORDER.filter((key) => visualAvailability[key]), [visualAvailability]);
  const currentVisualIndex = visualKey ? availableVisualKeys.indexOf(visualKey) : -1;
  const visualContextItems = [
    { label: "站点", value: pivotForm.station_name || "--" },
    { label: "要素", value: pivotForm.element || "--" },
    { label: "范围", value: rangeLabel },
    { label: "热力图时刻", value: heatmapLabel },
    { label: "选中格点", value: focusMeta ? `${formatMetric(focusMeta.lat, 3)}, ${formatMetric(focusMeta.lon, 3)}` : (pivotForm.lat && pivotForm.lon ? `${pivotForm.lat}, ${pivotForm.lon}` : "--") },
  ];
  const pivotSnapshotItems = [
    { label: "原始站点样本", value: rawSummary ? `${rawSummary.count} 个时刻` : "未加载" },
    { label: "对比样本", value: processedSummary ? `${processedSummary.count} 个时刻` : "未加载" },
    { label: "原始热力图", value: rawGridData ? `${rawGridData.lats.length} × ${rawGridData.lons.length}` : "未加载" },
    { label: "订正热力图", value: heatmapData ? `${heatmapData.lats.length} × ${heatmapData.lons.length}` : "未加载" },
  ];
  const moduleDetailItems = useMemo(() => {
    if (moduleKey === "settings") {
      const configured = Object.values(settings).filter(Boolean).length;
      return [
        { label: "已配置路径", value: `${configured} / 4`, detail: configured === 4 ? "基础数据源已经齐全" : "补齐后再进入后续流程" },
        { label: "可用站点", value: stations.length ? `${stations.length} 个` : "未读取", detail: "用于透视和预览的站点集合" },
        { label: "已登记模型", value: models.length ? `${models.length} 个` : "未读取", detail: "用于订正执行的模型清单" },
      ];
    }
    if (moduleKey === "import") {
      return [
        { label: "待导入文件", value: importCount ? `${importCount} 个` : "未检查", detail: "建议先检查文件质量再提交任务" },
        { label: "最近导入任务", value: tasks.filter((item) => item.task_type.startsWith("DataImport")).length.toString(), detail: "可在右侧实时任务里继续跟踪" },
        { label: "当前状态", value: importCount > 0 ? "可执行" : "待检查", detail: "先预览输入，再执行导入" },
      ];
    }
    if (moduleKey === "process") {
      return [
        { label: "已选要素", value: `${processForm.elements.length} 个`, detail: processForm.elements.join(" / ") || "至少选择一个要素" },
        { label: "时间跨度", value: `${processForm.start_year} - ${processForm.end_year}`, detail: "决定底表覆盖范围" },
        { label: "并行进程", value: processForm.num_workers, detail: "影响预处理吞吐效率" },
      ];
    }
    if (moduleKey === "train") {
      return [
        { label: "训练模型", value: trainForm.model, detail: "当前训练算法配置" },
        { label: "测试集配置", value: trainForm.test_set_values.split(/[,\n]/).map((item) => item.trim()).filter(Boolean).length.toString(), detail: "用于验证模型效果的切片数量" },
        { label: "训练季节", value: trainForm.season, detail: `时间范围 ${trainForm.start_year} - ${trainForm.end_year}` },
      ];
    }
    if (moduleKey === "correct") {
      return [
        { label: "选中模型", value: selectedModel?.model_name ?? "未选择", detail: selectedModel?.element ? `关联要素 ${selectedModel.element}` : "请先刷新模型列表" },
        { label: "执行范围", value: `${correctForm.start_year} - ${correctForm.end_year}`, detail: `块大小 ${correctForm.block_size}` },
        { label: "并行进程", value: correctForm.num_workers, detail: "影响订正吞吐与资源占用" },
      ];
    }
    if (moduleKey === "tasks") {
      return [
        { label: "当前筛选", value: taskFilter === "ALL" ? "全部任务" : taskFilter, detail: taskSearch ? `关键词 ${taskSearch}` : "可按状态或关键词收缩结果" },
        { label: "筛选结果", value: `${taskHistoryView.length} 条`, detail: "左侧为历史列表，右侧为父子任务细节" },
        { label: "排序方式", value: taskSort === "progress_desc" ? "进度从高到低" : taskSort === "progress_asc" ? "进度从低到高" : "名称排序", detail: "帮助快速定位异常任务" },
      ];
    }
    return [];
  }, [moduleKey, settings, stations.length, models.length, importCount, tasks, processForm, trainForm, selectedModel, correctForm, taskFilter, taskSearch, taskHistoryView.length, taskSort]);

  return (
    <div className="app-shell">
      <div className="background-grid" />
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">WC</div>
          <div>
            <div className="brand-title">气象订正工作台</div>
            <div className="brand-subtitle">围绕任务流与数据透视统一查看处理、训练、订正与分析结果</div>
          </div>
        </div>
        <div className="topbar-controls">
          <label className="compact-field">
            <span>后端地址</span>
            <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
          </label>
          <button className="ghost-button" onClick={() => void refreshBase()}>重新连接</button>
          <div className={`service-badge ${online ? "online" : "offline"}`}>{online ? "服务在线" : "服务离线"}</div>
        </div>
      </header>

      <main className="layout">
        <aside className="module-rail">
          <div className="rail-title">业务流程</div>
          {MODULES.map((item) => (
            <button key={item.key} className={`rail-item ${moduleKey === item.key ? "active" : ""}`} onClick={() => setModuleKey(item.key)}>
              <strong>{item.title}</strong>
              <small>{item.desc}</small>
            </button>
          ))}
        </aside>

        <section className="workspace">
          <div className="workspace-header">
            <div>
              <div className="section-eyebrow">Mission Control</div>
              <h1>{MODULES.find((item) => item.key === moduleKey)?.title}</h1>
              <p>{MODULES.find((item) => item.key === moduleKey)?.desc}</p>
            </div>
            <div className="summary-strip">
              <div className="summary-item"><span>执行中</span><strong>{stats.processing}</strong></div>
              <div className="summary-item"><span>已完成</span><strong>{stats.completed}</strong></div>
              <div className="summary-item"><span>失败</span><strong>{stats.failed}</strong></div>
              <div className="summary-item"><span>上次同步</span><strong>{lastSync}</strong></div>
            </div>
          </div>

          <div className="module-overview">
            <div className={`stage-card stage-${moduleStage.tone}`}>
              <span className="stage-label">当前阶段</span>
              <strong>{moduleStage.label}</strong>
              <p>{moduleStage.detail}</p>
            </div>
            <div className="module-hint"><strong>当前建议</strong><span>{moduleHint}</span></div>
          </div>

          <div className={`workspace-grid ${moduleKey === "pivot" ? "workspace-grid-pivot" : ""}`}>
            <section className="main-panel">
              {moduleKey !== "pivot" ? (
                <section className="module-detail-band">
                  <div className="module-detail-copy">
                    <span className="section-eyebrow">Module Focus</span>
                    <h2>{MODULES.find((item) => item.key === moduleKey)?.title}</h2>
                    <p>{moduleHint}</p>
                  </div>
                  <div className="module-detail-grid">
                    {moduleDetailItems.map((item) => (
                      <div className="module-detail-card" key={item.label}>
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                        <p>{item.detail}</p>
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}
              {moduleKey === "settings" ? <div className="panel-section"><div className="panel-header"><h2>数据源路径</h2><button className="primary-button" onClick={() => void saveSettings()} disabled={busy === "save-settings"}>{busy === "save-settings" ? "保存中..." : "保存配置"}</button></div><div className="field-grid two-col">{Object.entries(settings).map(([key, value]) => <label className="field-block" key={key}><span>{key}</span><input value={value} onChange={(event) => setSettings((current) => ({ ...current, [key]: event.target.value }))} /></label>)}</div></div> : null}
              {moduleKey === "import" ? <div className="panel-section"><div className="panel-header"><h2>导入准备</h2><div className="header-actions"><button className="ghost-button" onClick={() => void checkImportFiles()} disabled={busy === "check-import"}>{busy === "check-import" ? "检查中..." : "检查输入"}</button><button className="primary-button" onClick={() => void startImport()} disabled={busy === "start-import"}>{busy === "start-import" ? "启动中..." : "开始导入"}</button></div></div><div className="hero-metric"><div><span>待导入文件</span><strong>{importCount}</strong></div><p>建议先检查，再启动。任务进度会在右侧持续显示。</p></div><div className="list-panel">{importFiles.length > 0 ? importFiles.slice(0, 10).map((file) => <div className="file-row" key={file}><span>{file.split("\\").pop() ?? file}</span><small>{file}</small></div>) : <div className="empty-hint">先点击“检查输入”，确认待导入文件数量和来源路径。</div>}</div></div> : null}
              {moduleKey === "process" ? <div className="panel-section"><div className="panel-header"><h2>预处理配置</h2><button className="primary-button" onClick={() => void startProcess()} disabled={busy === "start-process"}>{busy === "start-process" ? "提交中..." : "开始预处理"}</button></div><div className="chip-row">{ELEMENTS.map((item) => <button key={item} className={`select-chip ${processForm.elements.includes(item) ? "selected" : ""}`} onClick={() => toggleList(item, "process")}>{item}</button>)}</div><div className="field-grid three-col"><label className="field-block"><span>开始年份</span><input value={processForm.start_year} onChange={(event) => setProcessForm((current) => ({ ...current, start_year: event.target.value }))} /></label><label className="field-block"><span>结束年份</span><input value={processForm.end_year} onChange={(event) => setProcessForm((current) => ({ ...current, end_year: event.target.value }))} /></label><label className="field-block"><span>工作进程数</span><input value={processForm.num_workers} onChange={(event) => setProcessForm((current) => ({ ...current, num_workers: event.target.value }))} /></label></div></div> : null}
              {moduleKey === "train" ? <div className="panel-section"><div className="panel-header"><h2>训练配置</h2><button className="primary-button" onClick={() => void startTrain()} disabled={busy === "start-train"}>{busy === "start-train" ? "提交中..." : "开始训练"}</button></div><div className="chip-row">{ELEMENTS.map((item) => <button key={item} className={`select-chip ${trainForm.element.includes(item) ? "selected" : ""}`} onClick={() => toggleList(item, "train")}>{item}</button>)}</div><div className="field-grid three-col"><label className="field-block"><span>开始年份</span><input value={trainForm.start_year} onChange={(event) => setTrainForm((current) => ({ ...current, start_year: event.target.value }))} /></label><label className="field-block"><span>结束年份</span><input value={trainForm.end_year} onChange={(event) => setTrainForm((current) => ({ ...current, end_year: event.target.value }))} /></label><label className="field-block"><span>提前停止轮数</span><input value={trainForm.early_stopping_rounds} onChange={(event) => setTrainForm((current) => ({ ...current, early_stopping_rounds: event.target.value }))} /></label></div><div className="field-grid two-col"><label className="field-block"><span>季节</span><select value={trainForm.season} onChange={(event) => setTrainForm((current) => ({ ...current, season: event.target.value }))}>{SEASONS.map((item) => <option key={item} value={item}>{item}</option>)}</select></label><label className="field-block"><span>模型</span><select value={trainForm.model} onChange={(event) => setTrainForm((current) => ({ ...current, model: event.target.value }))}><option value="XGBoost">XGBoost</option><option value="LightGBM">LightGBM</option></select></label></div><label className="field-block"><span>测试集取值</span><textarea rows={4} value={trainForm.test_set_values} onChange={(event) => setTrainForm((current) => ({ ...current, test_set_values: event.target.value }))} placeholder="例如：2022,2023" /></label></div> : null}
              {moduleKey === "correct" ? <div className="panel-section"><div className="panel-header"><h2>订正配置</h2><div className="header-actions"><button className="ghost-button" onClick={() => void refreshModels()} disabled={busy === "refresh-models"}>{busy === "refresh-models" ? "刷新中..." : "同步模型"}</button><button className="primary-button" onClick={() => void startCorrect()} disabled={busy === "start-correct"}>{busy === "start-correct" ? "提交中..." : "开始订正"}</button></div></div><div className="field-grid two-col"><label className="field-block"><span>已保存模型</span><select value={correctForm.model_path} onChange={(event) => { const found = models.find((item) => item.model_path === event.target.value); setCorrectForm((current) => ({ ...current, model_path: event.target.value, element: found?.element ?? current.element })); }}>{models.map((item) => <option key={item.model_path} value={item.model_path}>{item.model_name}</option>)}</select></label><label className="field-block"><span>气象要素</span><select value={correctForm.element} onChange={(event) => setCorrectForm((current) => ({ ...current, element: event.target.value }))}>{ELEMENTS.map((item) => <option key={item} value={item}>{item}</option>)}</select></label></div><div className="field-grid four-col"><label className="field-block"><span>开始年份</span><input value={correctForm.start_year} onChange={(event) => setCorrectForm((current) => ({ ...current, start_year: event.target.value }))} /></label><label className="field-block"><span>结束年份</span><input value={correctForm.end_year} onChange={(event) => setCorrectForm((current) => ({ ...current, end_year: event.target.value }))} /></label><label className="field-block"><span>块大小</span><input value={correctForm.block_size} onChange={(event) => setCorrectForm((current) => ({ ...current, block_size: event.target.value }))} /></label><label className="field-block"><span>进程数</span><input value={correctForm.num_workers} onChange={(event) => setCorrectForm((current) => ({ ...current, num_workers: event.target.value }))} /></label></div>{selectedModel ? <div className="model-highlight"><div><span>模型</span><strong>{selectedModel.model_name}</strong></div><div><span>关联任务</span><strong>{selectedModel.task_id}</strong></div><div><span>要素</span><strong>{selectedModel.element}</strong></div></div> : <div className="empty-hint">当前还没有可用模型。下一步：先完成训练，或点击“同步模型”刷新列表。</div>}</div> : null}
              {moduleKey === "pivot" ? (
                <div className="panel-section">
                  <section className="pivot-stage-hero">
                    <div className="pivot-stage-copy">
                      <span className="section-eyebrow">Operations View</span>
                      <h2>把原始审视、订正比对和格点诊断统一到一条分析流。</h2>
                      <p>先定筛选，再看结果，最后进入图形页细看空间分布和时序变化。</p>
                    </div>
                    <div className="pivot-stage-aside">
                      <div className="pivot-stage-item"><span>站点</span><strong>{pivotForm.station_name || "--"}</strong></div>
                      <div className="pivot-stage-item"><span>要素</span><strong>{pivotForm.element}</strong></div>
                      <div className="pivot-stage-item"><span>范围</span><strong>{rangeLabel}</strong></div>
                    </div>
                  </section>

                  <section className="pivot-toolbar-shell">
                    <div className="panel-header">
                      <h2>分析筛选</h2>
                    </div>
                    <div className="pivot-toolbar">
                    <div className="field-grid three-col">
                      <label className="field-block">
                        <span>站点</span>
                        <select value={pivotForm.station_name} onChange={(event) => setPivotForm((current) => ({ ...current, station_name: event.target.value }))}>
                          {stations.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
                        </select>
                      </label>
                      <label className="field-block">
                        <span>要素</span>
                        <select value={pivotForm.element} onChange={(event) => setPivotForm((current) => ({ ...current, element: event.target.value }))}>
                          {ELEMENTS.map((item) => <option key={item} value={item}>{item}</option>)}
                        </select>
                      </label>
                      <label className="field-block">
                        <span>热力图时刻</span>
                        <input type="datetime-local" value={pivotForm.heatmap_time} onChange={(event) => setPivotForm((current) => ({ ...current, heatmap_time: event.target.value }))} />
                      </label>
                    </div>
                    <div className="quick-range-row">
                      <span className="quick-range-label">快捷范围</span>
                      <button className="select-chip" type="button" onClick={() => void applyQuickRange(24)}>最近24小时</button>
                      <button className="select-chip" type="button" onClick={() => void applyQuickRange(72)}>最近3天</button>
                      <button className="select-chip" type="button" onClick={() => void applyQuickRange(168)}>最近7天</button>
                    </div>
                    <div className="field-grid four-col">
                      <label className="field-block"><span>开始时间</span><input type="datetime-local" value={pivotForm.start_time} onChange={(event) => setPivotForm((current) => ({ ...current, start_time: event.target.value }))} /></label>
                      <label className="field-block"><span>结束时间</span><input type="datetime-local" value={pivotForm.end_time} onChange={(event) => setPivotForm((current) => ({ ...current, end_time: event.target.value }))} /></label>
                      <label className="field-block"><span>纬度</span><input value={pivotForm.lat} onChange={(event) => setPivotForm((current) => ({ ...current, lat: event.target.value }))} placeholder="点击热力图自动填入" /></label>
                      <label className="field-block"><span>经度</span><input value={pivotForm.lon} onChange={(event) => setPivotForm((current) => ({ ...current, lon: event.target.value }))} placeholder="点击热力图自动填入" /></label>
                    </div>
                    </div>
                  </section>

                  <section className="pivot-kpis pivot-context-band">
                    <div className="summary-mini"><span>原始站点均值</span><strong>{formatMetric(rawSummary?.stationMean)}</strong></div>
                    <div className="summary-mini"><span>对比站点均值</span><strong>{formatMetric(processedSummary?.stationMean)}</strong></div>
                    <div className="summary-mini"><span>对比格点均值</span><strong>{formatMetric(processedSummary?.gridMean)}</strong></div>
                    <div className="summary-mini"><span>平均偏差</span><strong>{formatMetric(processedSummary?.meanBias)}</strong></div>
                  </section>

                  <section className="pivot-snapshot">
                    <div className="pivot-snapshot-copy">
                      <span className="section-eyebrow">Workspace Snapshot</span>
                      <h3>先确定时空范围，再进入图形页做细看。</h3>
                      <p>主页面承担筛选、状态和决策入口，图形页承担细节阅读。这样既不会把大图挤在工作台里，也更适合连续分析。</p>
                    </div>
                    <div className="pivot-snapshot-grid">
                      {pivotSnapshotItems.map((item) => (
                        <div className="pivot-snapshot-item" key={item.label}>
                          <span>{item.label}</span>
                          <strong>{item.value}</strong>
                        </div>
                      ))}
                    </div>
                  </section>

                  <div className="pivot-columns">
                    <section className="pivot-column">
                      <div className="pivot-column-head">
                        <div>
                          <span className="section-eyebrow">Raw Preview</span>
                          <h3>原始预览</h3>
                        </div>
                        <p>训练前先检查站点观测和原始格点分布。</p>
                      </div>
                      <div className="pivot-status-row">
                        {rawStatusItems.map((item) => <span key={item.label} className={`pivot-status-pill ${item.active ? "active" : ""}`}>{item.label} · {item.text}</span>)}
                      </div>
                      <div className="pivot-column-actions">
                        <button className="ghost-button" onClick={() => void loadRawStationPreview()} disabled={busy === "raw-station"}>{busy === "raw-station" ? "查询中..." : "原始站点曲线"}</button>
                        <button className="ghost-button" onClick={() => void loadRawGridHeatmap()} disabled={busy === "raw-grid-heatmap"}>{busy === "raw-grid-heatmap" ? "加载中..." : "原始格点热力图"}</button>
                        <button className="ghost-button" onClick={() => void loadRawGridTimeseries()} disabled={busy === "raw-grid-timeseries"}>{busy === "raw-grid-timeseries" ? "提交中..." : "原始格点时序"}</button>
                      </div>
                      {rawStationData ? <VisualLaunchCard title="原始站点曲线" detail={`站点 ${rawStationData.station_name}，范围 ${rangeLabel}`} accent="good" action={<button className="ghost-button" onClick={() => setVisualKey("raw-station")}>打开图形</button>} /> : <div className="empty-hint">还没有原始站点曲线。下一步：确认站点、要素和时间范围后，点击“原始站点曲线”。</div>}
                      {rawGridData ? <VisualLaunchCard title="原始格点热力图" detail={`时刻 ${heatmapLabel}，可在弹层里选点查看`} accent="good" action={<button className="ghost-button" onClick={() => setVisualKey("raw-grid")}>打开热力图</button>} /> : <div className="empty-hint">还没有原始格点热力图。下一步：确认要素和热力图时刻后，点击“原始格点热力图”。</div>}
                      {rawGridStatus && !(rawGridStatus.status === "COMPLETED" && rawGridSeriesData) ? <div className="detail-card"><div className="detail-row"><span>原始格点时序任务</span><strong>{statusLabel(rawGridStatus.status)}</strong></div><div className="detail-row"><span>提取进度</span><strong>{formatMetric(rawGridStatus.progress, 0)}%</strong></div><div className="progress-track"><div className="progress-fill" style={{ width: `${rawGridStatus.progress}%` }} /></div><p>{rawGridStatus.error || "正在提取原始格点时间序列，请稍候。"} </p></div> : null}
                      {rawGridSeriesData ? <VisualLaunchCard title="原始格点时序" detail={`范围 ${rangeLabel}，坐标 ${formatMetric(rawGridSeriesData.lat, 3)}, ${formatMetric(rawGridSeriesData.lon, 3)}`} accent="good" action={<button className="ghost-button" onClick={() => setVisualKey("raw-grid-series")}>打开图形</button>} /> : <div className="empty-hint">还没有原始格点时序。下一步：先点击热力图选点或输入经纬度，再点击“原始格点时序”。当前范围：{rangeLabel}。</div>}
                    </section>

                    <section className="pivot-column">
                      <div className="pivot-column-head">
                        <div>
                          <span className="section-eyebrow">Corrected Compare</span>
                          <h3>订正对比</h3>
                        </div>
                        <p>订正完成后再检查站点对比、空间分布和格点时序变化。</p>
                      </div>
                      <div className="pivot-status-row">
                        {compareStatusItems.map((item) => <span key={item.label} className={`pivot-status-pill ${item.active ? "active" : ""}`}>{item.label} · {item.text}</span>)}
                      </div>
                      <div className="pivot-column-actions">
                        <button className="ghost-button" onClick={() => void loadProcessedPivot()} disabled={busy === "pivot-processed"}>{busy === "pivot-processed" ? "查询中..." : "站点对比分析"}</button>
                        <button className="ghost-button" onClick={() => void loadHeatmap()} disabled={busy === "pivot-heatmap"}>{busy === "pivot-heatmap" ? "加载中..." : "订正前后热力图"}</button>
                        <button className="primary-button" onClick={() => void loadPivotTimeseries()} disabled={busy === "pivot-timeseries"}>{busy === "pivot-timeseries" ? "提交中..." : "订正前后时序"}</button>
                      </div>
                      {processedData ? <VisualLaunchCard title="站点对比分析" detail={`范围 ${rangeLabel}，站点实测与原始格点同屏对比`} accent="good" action={<button className="ghost-button" onClick={() => setVisualKey("processed")}>打开图形</button>} /> : <div className="empty-hint">还没有站点对比结果。下一步：先完成预处理，再点击“站点对比分析”。当前范围：{rangeLabel}。</div>}
                      {heatmapData ? <VisualLaunchCard title="订正前后热力图" detail={`时刻 ${heatmapLabel}，在弹层里查看前后空间分布`} accent="good" action={<button className="ghost-button" onClick={() => setVisualKey("compare-heatmap")}>打开热力图</button>} /> : <div className="empty-hint">还没有订正前后热力图。下一步：确认该时刻已有订正结果后，点击“订正前后热力图”。</div>}
                      <div className="focus-inspector">
                        <div className="panel-header tight">
                          <h2>选中格点</h2>
                          {focusMeta ? <span className="muted-label">{formatMetric(focusMeta.lat, 3)}, {formatMetric(focusMeta.lon, 3)}</span> : null}
                        </div>
                        {focusMeta ? <div className="model-highlight"><div><span>订正前</span><strong>{formatMetric(focusMeta.before, 3)}</strong></div><div><span>订正后</span><strong>{formatMetric(focusMeta.after, 3)}</strong></div><div><span>变化量</span><strong>{formatMetric((focusMeta.after ?? 0) - (focusMeta.before ?? 0), 3)}</strong></div></div> : <div className="empty-hint">点击热力图格点后，这里会显示该位置的前后差异。</div>}
                        {pivotSeriesStatus && !(pivotSeriesStatus.status === "COMPLETED" && pivotSeriesData) ? <div className="detail-card"><div className="detail-row"><span>订正前后时序任务</span><strong>{statusLabel(pivotSeriesStatus.status)}</strong></div><div className="detail-row"><span>提取进度</span><strong>{formatMetric(pivotSeriesStatus.progress, 0)}%</strong></div><div className="progress-track"><div className="progress-fill" style={{ width: `${pivotSeriesStatus.progress}%` }} /></div><p>{pivotSeriesStatus.progress_text || "系统正在生成格点订正前后对比曲线。"} </p></div> : null}
                        {pivotSeriesData ? <VisualLaunchCard title="订正前后时序" detail={`范围 ${rangeLabel}，可在弹层里放大查看前后曲线`} accent="good" action={<button className="ghost-button" onClick={() => setVisualKey("compare-series")}>打开图形</button>} /> : <div className="empty-hint">还没有订正前后时序。下一步：先在热力图中选点，再点击“订正前后时序”。当前范围：{rangeLabel}。</div>}
                      </div>
                    </section>
                  </div>
                </div>
              ) : null}
              {moduleKey === "tasks" ? <div className="panel-section"><div className="panel-header"><h2>任务历史</h2><button className="ghost-button" onClick={() => void refreshTasks()}>刷新列表</button></div><div className="chip-row">{(["ALL", "PROCESSING", "COMPLETED", "FAILED", "PENDING"] as TaskFilter[]).map((item) => <button key={item} className={`select-chip ${taskFilter === item ? "selected" : ""}`} onClick={() => setTaskFilter(item)}>{item === "ALL" ? "全部" : item === "PROCESSING" ? "运行中" : item === "COMPLETED" ? "已完成" : item === "FAILED" ? "失败" : "等待中"}</button>)}</div><div className="field-grid two-col compact-tools"><label className="field-block"><span>搜索任务</span><input value={taskSearch} onChange={(event) => setTaskSearch(event.target.value)} placeholder="任务名 / 类型 / ID" /></label><label className="field-block"><span>排序方式</span><select value={taskSort} onChange={(event) => setTaskSort(event.target.value as "progress_desc" | "progress_asc" | "name")}><option value="progress_desc">按进度从高到低</option><option value="progress_asc">按进度从低到高</option><option value="name">按名称排序</option></select></label></div><div className="task-table">{taskHistoryView.map((task) => <button key={task.task_id} className={`task-row ${selectedTaskId === task.task_id ? "selected" : ""}`} onClick={() => setSelectedTaskId(task.task_id)}><div className="task-row-main"><strong>{task.task_name}</strong><span className={`status-pill ${statusClass(task.status)}`}>{statusLabel(task.status)}</span></div><div className="task-row-meta"><span>{task.task_type}</span><span>{task.progress}%</span></div><div className="progress-track slim"><div className="progress-fill" style={{ width: `${task.progress}%` }} /></div></button>)}{taskHistoryView.length === 0 ? <div className="empty-hint">当前筛选条件下没有任务。可以切换状态筛选，或清空关键词后重试。</div> : null}</div></div> : null}
            </section>
            <aside className="side-panel">
              <section className="side-section"><div className="panel-header tight"><h2>实时任务</h2><span className="muted-label">{moduleTasks.length}</span></div><div className="status-legend"><span className="legend-item"><i className="legend-dot dot-processing" />运行中</span><span className="legend-item"><i className="legend-dot dot-completed" />已完成</span><span className="legend-item"><i className="legend-dot dot-failed" />失败</span></div>{moduleTasks.length > 0 ? moduleTasks.map((task) => <button key={task.task_id} className={`live-task ${selectedTaskId === task.task_id ? "selected" : ""}`} onClick={() => setSelectedTaskId(task.task_id)}><div className="live-task-top"><strong>{task.task_name}</strong><span className={`status-pill ${statusClass(task.status)}`}>{statusLabel(task.status)}</span></div><div className="live-task-meta"><span>{task.task_type}</span><span>{task.progress}%</span></div><div className="progress-track"><div className="progress-fill" style={{ width: `${task.progress}%` }} /></div><p>{task.progress_text || "等待下一次进度回传。"} </p></button>) : <div className="empty-hint">当前模块还没有任务。执行一次操作后，这里会自动开始跟踪。</div>}</section>
              <section className="side-section"><div className="panel-header tight"><h2>当前任务</h2>{taskDetail.parent.status === "PROCESSING" || taskDetail.parent.status === "PENDING" ? <button className="ghost-button danger" onClick={() => void cancelTask()} disabled={busy === "cancel-task"}>{busy === "cancel-task" ? "发送中..." : "取消任务"}</button> : null}</div>{taskDetail.parent.task_id ? <><div className="task-summary-grid"><div className="summary-mini"><span>总子任务</span><strong>{taskSummary.total}</strong></div><div className="summary-mini"><span>进行中</span><strong>{taskSummary.processing}</strong></div><div className="summary-mini"><span>已完成</span><strong>{taskSummary.completed}</strong></div><div className="summary-mini"><span>失败</span><strong>{taskSummary.failed}</strong></div></div><div className="detail-card"><div className="detail-row"><span>任务名</span><strong>{taskDetail.parent.task_name}</strong></div><div className="detail-row"><span>状态</span><strong>{statusLabel(taskDetail.parent.status)}</strong></div><div className="detail-row"><span>进度</span><strong>{taskDetail.parent.progress}%</strong></div><div className="progress-track"><div className="progress-fill" style={{ width: `${taskDetail.parent.progress}%` }} /></div><p>{taskDetail.parent.progress_text || "系统尚未返回更详细的进度描述。"} </p></div><div className="subtask-list">{taskDetail.sub_tasks.length > 0 ? taskDetail.sub_tasks.slice(0, 12).map((item) => <div className="subtask-item" key={item.task_id}><div className="subtask-top"><strong>{item.task_name}</strong><span className={`status-pill ${statusClass(item.status)}`}>{statusLabel(item.status)}</span></div><div className="progress-track slim"><div className="progress-fill" style={{ width: `${item.progress}%` }} /></div><small>{item.progress_text || `${item.progress}%`}</small></div>) : <div className="empty-hint">当前没有返回子任务详情。可以稍后刷新，或切换到其他任务查看。</div>}</div></> : <div className="empty-hint">选择一个任务后，这里会显示父任务和子任务进度。</div>}</section>
              <section className="side-section"><div className="panel-header tight"><h2>操作回执</h2><span className="muted-label">{logs.length}</span></div><div className="activity-list scroll-panel">{logs.length > 0 ? logs.map((item) => <div className={`activity-item ${item.tone}`} key={item.id}><div className="activity-top"><strong>{item.title}</strong></div><p>{item.detail}</p></div>) : <div className="empty-hint">最近的操作结果会显示在这里。</div>}</div></section>
            </aside>
          </div>
        </section>
      </main>

      {visualKey ? (
        <div className="visual-modal">
          <div className="visual-backdrop" onClick={() => setVisualKey(null)} />
          <div className="visual-sheet">
            <div className="visual-sheet-head">
              <div className="visual-head-copy">
                <span className="section-eyebrow">{VISUAL_META[visualKey].section}</span>
                <h2>{VISUAL_META[visualKey].title}</h2>
                <p>{VISUAL_META[visualKey].detail}</p>
              </div>
              <div className="visual-head-actions">
                <span className="muted-label">{availableVisualKeys.length > 0 && currentVisualIndex >= 0 ? `${currentVisualIndex + 1} / ${availableVisualKeys.length}` : ""}</span>
                <button className="ghost-button" onClick={() => setVisualKey(null)}>关闭</button>
              </div>
            </div>
            <div className="visual-context-strip">
              {visualContextItems.map((item) => (
                <div className="visual-context-item" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
            <div className="visual-shell">
              <aside className="visual-nav">
                {VISUAL_ORDER.map((key) => (
                  <button
                    key={key}
                    type="button"
                    className={`visual-nav-item ${visualKey === key ? "active" : ""}`}
                    disabled={!visualAvailability[key]}
                    onClick={() => visualAvailability[key] && setVisualKey(key)}
                  >
                    <span>{VISUAL_META[key].section}</span>
                    <strong>{VISUAL_META[key].title}</strong>
                    <small>{visualAvailability[key] ? "可查看" : "未生成"}</small>
                  </button>
                ))}
              </aside>
              <div className="visual-sheet-body">
                <div className="visual-stage">
                  {visualKey === "raw-station" && rawStationData ? <MultiLineChart labels={rawStationData.timestamps} series={rawStationSeries} /> : null}
                  {visualKey === "raw-grid" && rawGridData ? <>
                    {rawFocusMeta ? <div className="visual-focus-bar">
                      <div className="visual-focus-item"><span>选中纬度</span><strong>{formatMetric(rawFocusMeta.lat, 3)}</strong></div>
                      <div className="visual-focus-item"><span>选中经度</span><strong>{formatMetric(rawFocusMeta.lon, 3)}</strong></div>
                      <div className="visual-focus-item"><span>原始值</span><strong>{formatMetric(rawFocusMeta.value, 3)}</strong></div>
                    </div> : null}
                    <HeatmapMatrix title="原始格点热力图" subtitle={`时刻 ${heatmapLabel}`} values={rawGridData.values} lats={rawGridData.lats} lons={rawGridData.lons} focus={heatmapFocus} onSelect={selectHeatCell} />
                  </> : null}
                  {visualKey === "raw-grid-series" && rawGridSeriesData ? <MultiLineChart labels={rawGridSeriesData.timestamps} series={rawGridSeries} /> : null}
                  {visualKey === "processed" && processedData ? <><MultiLineChart labels={processedData.timestamps} series={processedSeries} /><div className="mini-chart-row"><Sparkline title="站点实测" color="#7dc2ff" values={processedData.station_values} /><Sparkline title="原始格点" color="#ffd28a" values={processedData.grid_values} /></div></> : null}
                  {visualKey === "compare-heatmap" && heatmapData ? <>
                    {focusMeta ? <div className="visual-focus-bar">
                      <div className="visual-focus-item"><span>选中纬度</span><strong>{formatMetric(focusMeta.lat, 3)}</strong></div>
                      <div className="visual-focus-item"><span>选中经度</span><strong>{formatMetric(focusMeta.lon, 3)}</strong></div>
                      <div className="visual-focus-item"><span>订正前</span><strong>{formatMetric(focusMeta.before, 3)}</strong></div>
                      <div className="visual-focus-item"><span>订正后</span><strong>{formatMetric(focusMeta.after, 3)}</strong></div>
                    </div> : null}
                    <div className="heatmap-layout"><HeatmapMatrix title="订正前热力图" subtitle={`时刻 ${heatmapLabel}`} values={heatmapData.values_before} lats={heatmapData.lats} lons={heatmapData.lons} focus={heatmapFocus} onSelect={selectHeatCell} /><HeatmapMatrix title="订正后热力图" subtitle={`时刻 ${heatmapLabel}`} values={heatmapData.values_after} lats={heatmapData.lats} lons={heatmapData.lons} focus={heatmapFocus} onSelect={selectHeatCell} /></div>
                  </> : null}
                  {visualKey === "compare-series" && pivotSeriesData ? <MultiLineChart labels={pivotSeriesData.timestamps} series={pivotTimeseriesSeries} /> : null}
                </div>
                <div className="visual-insights">
                  <div className="visual-insight-card">
                    <span>当前视图</span>
                    <strong>{VISUAL_META[visualKey].title}</strong>
                    <p>{VISUAL_META[visualKey].detail}</p>
                  </div>
                  <div className="visual-insight-card">
                    <span>分析提示</span>
                    <strong>{visualKey === "raw-grid" || visualKey === "compare-heatmap" ? "点击格点可同步经纬度" : "结合时间范围判断变化节奏"}</strong>
                    <p>{visualKey === "compare-heatmap" || visualKey === "compare-series" ? "如果没有订正结果，请先返回工作台确认当前要素与时刻已经完成订正。" : "训练前先从原始预览确认数据质量，再切换到订正对比查看效果。"}</p>
                  </div>
                  <div className="visual-insight-card">
                    <span>快捷操作</span>
                    <strong>Esc 关闭，左右方向键切换</strong>
                    <p>保留当前筛选上下文，不需要返回主页面重新选择条件。</p>
                  </div>
                </div>
                <div className="visual-close-hint">点击遮罩、右上角关闭按钮，或按 Esc 都可以退出当前图形页。</div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

