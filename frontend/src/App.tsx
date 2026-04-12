import { useEffect, useMemo, useState, type ReactNode } from "react";

/* ===== 类型定义 ===== */

type ModuleKey =
  | "dashboard"
  | "settings"
  | "import"
  | "process"
  | "train"
  | "correct"
  | "pivot"
  | "multieval"
  | "tasks";

type TaskStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED" | "IDLE" | "UNKNOWN";

type Task = {
  task_id: string;
  task_name: string;
  task_type: string;
  status: string;
  progress: number;
  progress_text: string;
};

type TaskDetail = { parent: Task; sub_tasks: Task[] };

type ModelRecord = {
  task_id: string;
  model_name: string;
  element: string;
  model_path: string;
};

type LogItem = {
  id: string;
  title: string;
  detail: string;
  tone: "info" | "success" | "error";
};

type TaskFilter = "ALL" | "PROCESSING" | "COMPLETED" | "FAILED" | "PENDING";

type StationOption = { name: string; raw: unknown };

/* 数据预览类型 */
type RawStationData = {
  station_name: string;
  lat: number;
  lon: number;
  timestamps: string[];
  values: Array<number | null>;
};

type RawGridHeatmapData = {
  lats: number[];
  lons: number[];
  values: Array<Array<number | null>>;
};

type RawGridTimeseriesData = {
  lat: number;
  lon: number;
  timestamps: string[];
  values: Array<number | null>;
};

type PivotProcessedData = {
  timestamps: string[];
  station_values: Array<number | null>;
  grid_values: Array<number | null>;
};

type PivotHeatmapData = {
  lats: number[];
  lons: number[];
  values_before: Array<Array<number | null>>;
  values_after: Array<Array<number | null>>;
};

type PivotTimeseriesData = {
  timestamps: string[];
  values_before: Array<number | null>;
  values_after: Array<number | null>;
};

/* 模型训练结果类型 */
type LossesData = {
  epochs: number[];
  train_losses: number[];
  test_losses: number[];
};

type MetricsData = {
  testset_true: Record<string, number>;
  testset_pred: Record<string, number>;
};

/* 导出任务类型 */
type ExportStatus = {
  task_id: string;
  status: string;
  progress: number;
  progress_text: string;
  download_url: string | null;
};

/* 模型评估结果类型 */
type ModelEvalResult = {
  timestamps: string[];
  station_values: Array<number | null>;
  grid_values: Array<number | null>;
  pred_values: Array<{
    model_name: string;
    pred_values: Array<number | null>;
  }>;
  metrics: Array<{
    station_name: string;
    model_name: string;
    metrics: Record<string, number>;
  }>;
};

/* 模型排名结果类型 */
type RankedModel = {
  model_name: string;
  model_id: string;
  task_id: string;
  season: string;
  metrics: Record<string, number>;
};

type ModelRankResult = {
  filter_conditions: Record<string, unknown>;
  total_models_found: number;
  total_metrics_loaded: number;
  ranked_models: RankedModel[];
};

/* 多站点评估结果类型 */
type StationEvalResult = {
  station_id: string;
  station_name: string;
  lat: number;
  lon: number;
  model_cc: number;
  model_rmse: number;
  model_mae: number;
  model_mre: number;
  model_mbe: number;
  model_r2: number;
  grid_cc: number;
  grid_rmse: number;
  grid_mae: number;
  grid_mre: number;
  grid_mbe: number;
  grid_r2: number;
  diff_cc: number;
  diff_cc_improved: boolean;
  diff_rmse: number;
  diff_rmse_improved: boolean;
  diff_mae: number;
  diff_mae_improved: boolean;
  diff_mre: number;
  diff_mre_improved: boolean;
  diff_mbe: number;
  diff_mbe_improved: boolean;
  diff_r2: number;
  diff_r2_improved: boolean;
};

type MultiEvalSummary = {
  total_stations: number;
  cc: { improved_count: number; degraded_count: number };
  rmse: { improved_count: number; degraded_count: number };
  mae: { improved_count: number; degraded_count: number };
  mre: { improved_count: number; degraded_count: number };
  mbe: { improved_count: number; degraded_count: number };
  r2: { improved_count: number; degraded_count: number };
};

/* ===== 常量 ===== */

const BASE_URL_KEY = "weather-correction-base-url";

const ELEMENTS = [
  "温度",
  "相对湿度",
  "过去1小时降水量",
  "2分钟平均风速",
];

const SEASONS = ["全年", "春季", "夏季", "秋季", "冬季"];

const METRIC_NAMES = ["CC", "RMSE", "MAE", "MRE", "MBE", "R2"];

const MODULES: Array<{ key: ModuleKey; title: string; desc: string }> = [
  { key: "dashboard", title: "仪表盘", desc: "总览工作流进度与系统状态" },
  { key: "settings", title: "数据源", desc: "配置基础数据路径" },
  { key: "import", title: "数据导入", desc: "检查并导入站点数据" },
  { key: "process", title: "预处理", desc: "按时间范围生成训练底表" },
  { key: "train", title: "模型训练", desc: "配置参数并训练模型" },
  { key: "correct", title: "数据订正", desc: "使用模型订正格点数据" },
  { key: "pivot", title: "数据透视", desc: "分析对比与可视化" },
  { key: "multieval", title: "多站点评估", desc: "批量评估模型效果" },
  { key: "tasks", title: "任务监控", desc: "查看任务状态与进度" },
];

const EMPTY_TASK: Task = {
  task_id: "",
  task_name: "",
  task_type: "",
  status: "IDLE",
  progress: 0,
  progress_text: "",
};

/* ===== 工具函数 ===== */

function clampProgress(value: unknown): number {
  const n = Number(value ?? 0);
  return Number.isNaN(n) ? 0 : Math.max(0, Math.min(100, n));
}

function mapTask(raw: Record<string, unknown>): Task {
  return {
    task_id: String(raw.task_id ?? ""),
    task_name: String(raw.task_name ?? "未命名任务"),
    task_type: String(raw.task_type ?? ""),
    status: String(raw.status ?? "UNKNOWN"),
    progress: clampProgress(raw.progress ?? raw.cur_progress),
    progress_text: String(
      raw.progress_text ?? raw.pregress_text ?? ""
    ),
  };
}

function statusClass(status: string): string {
  if (status === "COMPLETED") return "status-completed";
  if (status === "PROCESSING") return "status-processing";
  if (status === "FAILED") return "status-failed";
  if (status === "PENDING") return "status-pending";
  return "status-idle";
}

function statusLabel(status: string): string {
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
      if (Array.isArray(item) && item.length > 0)
        return { name: String(item[0] ?? ""), raw: item };
      if (item && typeof item === "object" && "name" in item)
        return {
          name: String((item as { name?: unknown }).name ?? ""),
          raw: item,
        };
      return { name: String(item ?? ""), raw: item };
    })
    .filter((item) => item.name);
}

function toApiDateTime(value: string): string {
  if (!value) return "";
  return value.length === 16 ? `${value}:00` : value;
}

function shiftHours(
  baseValue: string,
  hours: number
): { start: string; end: string } {
  const base = new Date(baseValue);
  if (Number.isNaN(base.getTime())) return { start: "", end: "" };
  const start = new Date(base.getTime() - hours * 60 * 60 * 1000);
  const pad = (v: number) => `${v}`.padStart(2, "0");
  const toLocalInput = (v: Date) =>
    `${v.getFullYear()}-${pad(v.getMonth() + 1)}-${pad(v.getDate())}T${pad(v.getHours())}:${pad(v.getMinutes())}`;
  return { start: toLocalInput(start), end: toLocalInput(base) };
}

function formatAxisTick(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const pad = (v: number) => `${v}`.padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:00`;
}

function fmt(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "--";
  return value.toFixed(digits);
}

function average(values: Array<number | null | undefined>): number | null {
  const valid = values.filter(
    (v): v is number => typeof v === "number" && Number.isFinite(v)
  );
  if (!valid.length) return null;
  return valid.reduce((s, v) => s + v, 0) / valid.length;
}

function diffAverage(
  a: Array<number | null | undefined>,
  b: Array<number | null | undefined>
): number | null {
  const pairs = a
    .map((v, i) =>
      typeof v === "number" && typeof b[i] === "number"
        ? v - (b[i] as number)
        : null
    )
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!pairs.length) return null;
  return pairs.reduce((s, v) => s + v, 0) / pairs.length;
}

function flattenMatrix(
  values: Array<Array<number | null>>
): number[] {
  return values
    .flat()
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
}

function colorForValue(
  value: number | null,
  min: number,
  max: number
): string {
  if (value == null || !Number.isFinite(value))
    return "rgba(255,255,255,0.06)";
  if (min === max) return "hsl(180 70% 50%)";
  const ratio = (value - min) / (max - min);
  const hue = 200 - ratio * 180;
  const light = 25 + ratio * 35;
  return `hsl(${hue} 75% ${light}%)`;
}

function buildLinePath(
  values: Array<number | null>,
  width: number,
  height: number
): { path: string; min: number; max: number } {
  const points = values
    .map((v, i) => ({ v, i }))
    .filter(
      (p): p is { v: number; i: number } =>
        typeof p.v === "number" && Number.isFinite(p.v)
    );
  if (!points.length) return { path: "", min: 0, max: 0 };
  const min = Math.min(...points.map((p) => p.v));
  const max = Math.max(...points.map((p) => p.v));
  const range = max - min || 1;
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const path = points
    .map((p, idx) => {
      const x = p.i * step;
      const y = height - ((p.v - min) / range) * height;
      return `${idx === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
  return { path, min, max };
}

/* ===== 通用 UI 组件 ===== */

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`status-pill ${statusClass(status)}`}>
      {statusLabel(status)}
    </span>
  );
}

function ProgressBar({
  value,
  slim,
}: {
  value: number;
  slim?: boolean;
}) {
  return (
    <div className={`progress-track${slim ? " slim" : ""}`}>
      <div
        className="progress-fill"
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

/* ===== 图表组件 ===== */

function LineChart({
  labels,
  series,
  width = 700,
  height = 220,
  pad = 24,
}: {
  labels: string[];
  series: Array<{ name: string; color: string; values: Array<number | null> }>;
  width?: number;
  height?: number;
  pad?: number;
}) {
  const valid = series.flatMap((s) =>
    s.values.filter((v): v is number => typeof v === "number" && Number.isFinite(v))
  );
  const min = valid.length ? Math.min(...valid) : 0;
  const max = valid.length ? Math.max(...valid) : 1;
  const range = max - min || 1;
  const xStep =
    labels.length > 1
      ? (width - pad * 2) / (labels.length - 1)
      : width - pad * 2;

  return (
    <div className="chart-card">
      <div className="chart-head">
        <div>
          <strong>趋势对比</strong>
          <small>
            {labels[0] ? `${formatAxisTick(labels[0])} → ${formatAxisTick(labels[labels.length - 1])}` : ""}
          </small>
        </div>
        <div className="chart-legend">
          {series.map((s) => (
            <span className="legend-item" key={s.name}>
              <i
                className="legend-dot"
                style={{ background: s.color }}
              />
              {s.name}
            </span>
          ))}
        </div>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="chart-svg"
      >
        {[0, 1, 2, 3].map((i) => {
          const y = pad + ((height - pad * 2) / 3) * i;
          return (
            <line
              key={i}
              x1={pad}
              y1={y}
              x2={width - pad}
              y2={y}
              className="chart-grid-line"
            />
          );
        })}
        {series.map((s) => {
          const pts = s.values
            .map((v, i) => {
              if (typeof v !== "number" || !Number.isFinite(v))
                return null;
              const x = pad + i * xStep;
              const y =
                height -
                pad -
                ((v - min) / range) * (height - pad * 2);
              return `${x},${y}`;
            })
            .filter(Boolean)
            .join(" ");
          return (
            <polyline
              key={s.name}
              points={pts}
              fill="none"
              stroke={s.color}
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          );
        })}
        <text x={pad} y={16} className="chart-axis-label">
          {fmt(max)}
        </text>
        <text x={pad} y={height - 6} className="chart-axis-label">
          {fmt(min)}
        </text>
      </svg>
    </div>
  );
}

function HeatmapMatrix({
  title,
  values,
  lats,
  lons,
  focus,
  onSelect,
  subtitle,
}: {
  title: string;
  values: Array<Array<number | null>>;
  lats: number[];
  lons: number[];
  focus: { row: number; col: number } | null;
  onSelect: (row: number, col: number) => void;
  subtitle?: string;
}) {
  const all = useMemo(() => flattenMatrix(values), [values]);
  const min = all.length ? Math.min(...all) : 0;
  const max = all.length ? Math.max(...all) : 1;
  const rows = Math.max(values.length, 1);
  const cols = Math.max(lons.length, 1);
  const w = Math.max(Math.min((320 * cols) / rows, 720), 200);

  return (
    <div className="heatmap-card">
      <div className="chart-head">
        <div>
          <strong>{title}</strong>
          {subtitle ? (
            <small>{subtitle}</small>
          ) : null}
        </div>
        <small>
          {fmt(min)} ~ {fmt(max)}
        </small>
      </div>
      <div
        className="heatmap-grid"
        style={{
          gridTemplateColumns: `repeat(${cols}, minmax(6px, 1fr))`,
          width: `min(100%, ${w}px)`,
          marginInline: "auto",
        }}
      >
        {values.map((row, ri) =>
          row.map((cell, ci) => (
            <button
              key={`${ri}-${ci}`}
              type="button"
              className={`heat-cell${focus?.row === ri && focus?.col === ci ? " selected" : ""}`}
              style={{ background: colorForValue(cell, min, max) }}
              title={`lat ${fmt(lats[ri], 3)} / lon ${fmt(lons[ci], 3)} / val ${fmt(cell, 3)}`}
              onClick={() => onSelect(ri, ci)}
            />
          ))
        )}
      </div>
      <div className="heatmap-axis">
        <span>
          纬度{lats.length ? ` ${fmt(lats[0], 2)} ~ ${fmt(lats[lats.length - 1], 2)}` : " --"}
        </span>
        <span>
          经度{lons.length ? ` ${fmt(lons[0], 2)} ~ ${fmt(lons[lons.length - 1], 2)}` : " --"}
        </span>
      </div>
    </div>
  );
}

function Sparkline({
  title,
  color,
  values,
}: {
  title: string;
  color: string;
  values: Array<number | null>;
}) {
  const { path, min, max } = useMemo(
    () => buildLinePath(values, 640, 60),
    [values]
  );
  return (
    <div className="sparkline-item">
      <strong>{title}</strong>
      <small>
        {fmt(min)} ~ {fmt(max)}
      </small>
      <svg viewBox="0 0 640 60" className="sparkline-svg">
        <path
          d={path}
          fill="none"
          stroke={color}
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

/* ===== 主应用 ===== */

export default function App() {
  /* ----- 全局状态 ----- */
  const [baseUrl, setBaseUrl] = useState(
    () => localStorage.getItem(BASE_URL_KEY) ?? "http://127.0.0.1:8000"
  );
  const [moduleKey, setModuleKey] = useState<ModuleKey>("dashboard");
  const [online, setOnline] = useState(false);
  const [busy, setBusy] = useState("");
  const [lastSync, setLastSync] = useState("--:--:--");

  /* 基础数据 */
  const [settings, setSettings] = useState({
    station_data_dir: "",
    grid_data_dir: "",
    station_info_path: "",
    dem_data_path: "",
  });
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [stations, setStations] = useState<StationOption[]>([]);

  /* 任务系统 */
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [taskFilter, setTaskFilter] = useState<TaskFilter>("ALL");
  const [taskSearch, setTaskSearch] = useState("");
  const [taskDetail, setTaskDetail] = useState<TaskDetail>({
    parent: EMPTY_TASK,
    sub_tasks: [],
  });

  /* 日志 */
  const [logs, setLogs] = useState<LogItem[]>([]);

  /* 导入 */
  const [importCount, setImportCount] = useState(0);
  const [importFiles, setImportFiles] = useState<string[]>([]);

  /* 预处理 */
  const [processForm, setProcessForm] = useState({
    elements: [...ELEMENTS],
    start_year: "2008",
    end_year: "2023",
    num_workers: "48",
  });

  /* 训练 */
  const [trainForm, setTrainForm] = useState({
    element: [...ELEMENTS],
    start_year: "2008",
    end_year: "2023",
    season: "全年",
    split_method: "按年份划分",
    test_set_values: "2022,2023",
    model: "XGBoost",
    early_stopping_rounds: "150",
  });
  const [modelConfig, setModelConfig] = useState<Record<string, unknown>>({});
  const [configModel, setConfigModel] = useState("XGBoost");
  const [configElement, setConfigElement] = useState("温度");
  const [lossesData, setLossesData] = useState<LossesData | null>(null);
  const [metricsData, setMetricsData] = useState<MetricsData | null>(null);

  /* 订正 */
  const [correctForm, setCorrectForm] = useState({
    model_path: "",
    element: "温度",
    start_year: "2008",
    end_year: "2023",
    season: "全年",
    block_size: "100",
    num_workers: "48",
  });

  /* 透视 */
  const [pivotForm, setPivotForm] = useState({
    station_name: "",
    element: "温度",
    start_time: "2023-01-01T00:00",
    end_time: "2023-01-03T00:00",
    heatmap_time: "2023-01-01T00:00",
    lat: "",
    lon: "",
  });
  const [rawStationData, setRawStationData] =
    useState<RawStationData | null>(null);
  const [rawGridData, setRawGridData] =
    useState<RawGridHeatmapData | null>(null);
  const [rawGridTaskId, setRawGridTaskId] = useState("");
  const [rawGridSeriesData, setRawGridSeriesData] =
    useState<RawGridTimeseriesData | null>(null);
  const [processedData, setProcessedData] =
    useState<PivotProcessedData | null>(null);
  const [heatmapData, setHeatmapData] =
    useState<PivotHeatmapData | null>(null);
  const [heatmapFocus, setHeatmapFocus] = useState<{
    row: number;
    col: number;
  } | null>(null);
  const [pivotSeriesTaskId, setPivotSeriesTaskId] = useState("");
  const [pivotSeriesData, setPivotSeriesData] =
    useState<PivotTimeseriesData | null>(null);

  /* 导出 */
  const [exportTaskId, setExportTaskId] = useState("");
  const [exportSource, setExportSource] = useState<"preview" | "pivot">("preview");
  const [exportStatus, setExportStatus] = useState<ExportStatus | null>(null);

  /* 模型评估 */
  const [modelEvalTaskId, setModelEvalTaskId] = useState("");
  const [modelEvalResult, setModelEvalResult] =
    useState<ModelEvalResult | null>(null);

  /* 模型排名 */
  const [rankTaskId, setRankTaskId] = useState("");
  const [rankResult, setRankResult] = useState<ModelRankResult | null>(null);

  /* 多站点评估 */
  const [multiEvalForm, setMultiEvalForm] = useState({
    model_name: "XGBoost" as "XGBoost" | "LightGBM",
    element: "温度",
    model_file: "",
    start_year: "2008",
    end_year: "2023",
    season: "全年",
  });
  const [multiEvalTaskId, setMultiEvalTaskId] = useState("");
  const [multiEvalResult, setMultiEvalResult] = useState<{
    results: StationEvalResult[];
    summary: MultiEvalSummary;
  } | null>(null);

  /* ----- 日志 ----- */
  function addLog(
    title: string,
    detail: string,
    tone: LogItem["tone"]
  ) {
    setLogs((prev) =>
      [
        { id: `${Date.now()}-${Math.random()}`, title, detail, tone },
        ...prev,
      ].slice(0, 10)
    );
  }

  /* ----- API 工具 ----- */
  async function api<T>(
    path: string,
    init?: RequestInit
  ): Promise<T> {
    const res = await fetch(
      `${baseUrl.replace(/\/$/, "")}${path}`,
      init
    );
    const text = await res.text();
    let data: unknown = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = text;
    }
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      if (typeof data === "string" && data) detail = data;
      if (typeof data === "object" && data && "detail" in data) {
        const v = (data as { detail?: unknown }).detail;
        detail = typeof v === "string" ? v : JSON.stringify(v);
      }
      throw new Error(detail);
    }
    return data as T;
  }

  async function runAction(
    key: string,
    work: () => Promise<void>
  ) {
    try {
      setBusy(key);
      await work();
      await refreshTasks();
    } finally {
      setBusy("");
    }
  }

  /* ----- 数据刷新 ----- */
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
        setCorrectForm((c) => ({
          ...c,
          model_path: c.model_path || nextModels[0].model_path,
          element: c.element || nextModels[0].element,
        }));
      }
      const nextStations = parseStations(stationData);
      setStations(nextStations);
      if (nextStations[0]) {
        setPivotForm((c) => ({
          ...c,
          station_name: c.station_name || nextStations[0].name,
        }));
      }
      setOnline(true);
      setLastSync(
        new Date().toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        })
      );
      localStorage.setItem(BASE_URL_KEY, baseUrl);
    } catch {
      setOnline(false);
    }
  }

  async function refreshTasks() {
    try {
      const history = await api<Array<Record<string, unknown>>>(
        "/task_operate/history?limit=24"
      );
      const next = history.map(mapTask);
      setTasks(next);
      if (!selectedTaskId && next[0]) setSelectedTaskId(next[0].task_id);
    } catch {
      /* 静默 */
    }
  }

  async function refreshTaskDetail(taskId: string) {
    if (!taskId) return;
    try {
      const detail = await api<{
        parent: Record<string, unknown>;
        sub_tasks: Array<Record<string, unknown>>;
      }>(`/task_operate/status/${encodeURIComponent(taskId)}/details`);
      setTaskDetail({
        parent: mapTask(detail.parent),
        sub_tasks: (detail.sub_tasks ?? []).map(mapTask),
      });
    } catch {
      try {
        const parent = await api<Record<string, unknown>>(
          `/task_operate/status/${encodeURIComponent(taskId)}`
        );
        setTaskDetail({ parent: mapTask(parent), sub_tasks: [] });
      } catch {
        /* 静默 */
      }
    }
  }

  /* ----- Effects ----- */
  useEffect(() => {
    void refreshBase();
    void refreshTasks();
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      void refreshBase();
      void refreshTasks();
    }, 6000);
    return () => clearInterval(timer);
  }, [baseUrl]);

  useEffect(() => {
    if (!selectedTaskId) return;
    void refreshTaskDetail(selectedTaskId);
    const timer = setInterval(
      () => void refreshTaskDetail(selectedTaskId),
      3000
    );
    return () => clearInterval(timer);
  }, [selectedTaskId, baseUrl]);

  /* ----- 计算值 ----- */
  const stats = useMemo(
    () => ({
      processing: tasks.filter((t) => t.status === "PROCESSING").length,
      completed: tasks.filter((t) => t.status === "COMPLETED").length,
      failed: tasks.filter((t) => t.status === "FAILED").length,
    }),
    [tasks]
  );

  const filteredTasks = tasks
    .filter((t) => taskFilter === "ALL" || t.status === taskFilter)
    .filter((t) => {
      const q = taskSearch.trim().toLowerCase();
      if (!q) return true;
      return `${t.task_name} ${t.task_type} ${t.task_id}`
        .toLowerCase()
        .includes(q);
    });

  const moduleTasks = filteredTasks
    .filter((t) => taskModule(t.task_type) === moduleKey)
    .slice(0, 6);

  const taskSummary = useMemo(
    () => ({
      total: taskDetail.sub_tasks.length,
      completed: taskDetail.sub_tasks.filter(
        (t) => t.status === "COMPLETED"
      ).length,
      failed: taskDetail.sub_tasks.filter((t) => t.status === "FAILED")
        .length,
      processing: taskDetail.sub_tasks.filter(
        (t) => t.status === "PROCESSING"
      ).length,
    }),
    [taskDetail.sub_tasks]
  );

  const selectedModel = models.find(
    (m) => m.model_path === correctForm.model_path
  ) ?? models[0];

  const currentModule = MODULES.find((m) => m.key === moduleKey);

  /* ----- 模块 API 操作 ----- */

  async function saveSettings() {
    await runAction("save-settings", async () => {
      await api("/settings/source-dirs", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      addLog("保存成功", "数据源路径已更新", "success");
      await refreshBase();
    });
  }

  async function checkImportFiles() {
    await runAction("check-import", async () => {
      const r = await api<{ count: number; files: string[] }>(
        "/data-import/check"
      );
      setImportCount(r.count);
      setImportFiles(r.files ?? []);
      addLog("检查完成", `识别到 ${r.count} 个待导入文件`, "success");
    });
  }

  async function startImport() {
    await runAction("start-import", async () => {
      const r = await api<{ task_id: string; message: string }>(
        "/data-import/start",
        { method: "POST" }
      );
      setSelectedTaskId(r.task_id);
      addLog("导入已启动", r.message, "success");
    });
  }

  async function startProcess() {
    await runAction("start-process", async () => {
      const r = await api<{ task_id: string; message: string }>(
        "/data-process/start",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            elements: processForm.elements,
            start_year: processForm.start_year,
            end_year: processForm.end_year,
            num_workers: Number(processForm.num_workers),
          }),
        }
      );
      setSelectedTaskId(r.task_id);
      addLog("预处理已启动", r.message, "success");
    });
  }

  function toggleProcessElement(el: string) {
    setProcessForm((c) => ({
      ...c,
      elements: c.elements.includes(el)
        ? c.elements.filter((e) => e !== el)
        : [...c.elements, el],
    }));
  }

  function toggleTrainElement(el: string) {
    setTrainForm((c) => ({
      ...c,
      element: c.element.includes(el)
        ? c.element.filter((e) => e !== el)
        : [...c.element, el],
    }));
  }

  async function startTrain() {
    await runAction("start-train", async () => {
      const r = await api<{ task_id: string; message: string }>(
        "/model-train/start",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            element: trainForm.element,
            start_year: trainForm.start_year,
            end_year: trainForm.end_year,
            season: trainForm.season,
            split_method: trainForm.split_method,
            test_set_values: trainForm.test_set_values
              .split(/[,\n]/)
              .map((s) => s.trim())
              .filter(Boolean),
            model: trainForm.model,
            early_stopping_rounds: trainForm.early_stopping_rounds,
          }),
        }
      );
      setSelectedTaskId(r.task_id);
      addLog("训练已启动", r.message, "success");
    });
  }

  async function fetchModelConfig() {
    await runAction("fetch-config", async () => {
      const r = await api<Record<string, unknown>>(
        `/model-train/model-config/${configModel}/${configElement}`
      );
      setModelConfig(r);
      addLog(
        "配置已加载",
        `${configModel} / ${configElement} 参数已读取`,
        "success"
      );
    });
  }

  async function updateModelConfig() {
    await runAction("update-config", async () => {
      const r = await api<{ message: string }>(
        `/model-train/model-config/${configModel}/${configElement}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ params: modelConfig }),
        }
      );
      addLog("配置已更新", r.message, "success");
    });
  }

  async function fetchLosses() {
    await runAction("fetch-losses", async () => {
      const r = await api<LossesData>("/model-train/get-losses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_id: taskDetail.parent.task_id,
          model: trainForm.model,
          element: trainForm.element[0] ?? "温度",
          start_year: trainForm.start_year,
          end_year: trainForm.end_year,
          season: trainForm.season,
          split_method: trainForm.split_method,
        }),
      });
      setLossesData(r);
      addLog(
        "损失曲线已加载",
        `${r.epochs.length} 个 epoch`,
        "success"
      );
    });
  }

  async function fetchMetrics() {
    await runAction("fetch-metrics", async () => {
      const r = await api<MetricsData>(
        "/model-train/get-metrics-testset-all",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            task_id: taskDetail.parent.task_id,
            model: trainForm.model,
            element: trainForm.element[0] ?? "温度",
            start_year: trainForm.start_year,
            end_year: trainForm.end_year,
            season: trainForm.season,
            split_method: trainForm.split_method,
          }),
        }
      );
      setMetricsData(r);
      addLog("评估指标已加载", "测试集指标已读取", "success");
    });
  }

  async function saveModelRecord(taskId: string) {
    await runAction("save-model", async () => {
      const r = await api<{ message: string }>(
        `/model-train/save-model-record?task_id=${encodeURIComponent(taskId)}`
      );
      addLog("模型已保存", r.message, "success");
      await refreshBase();
    });
  }

  async function deleteModelRecord(taskId: string) {
    await runAction("delete-model", async () => {
      const r = await api<{ message: string }>(
        `/model-train/delete-model-record/${encodeURIComponent(taskId)}`,
        { method: "DELETE" }
      );
      addLog("模型已删除", r.message, "info");
      await refreshBase();
    });
  }

  /* ----- 模块面板渲染 ----- */

  function renderDashboard(): ReactNode {
    const steps = [
      {
        key: "settings",
        title: "配置数据源",
        done: !!(settings.station_data_dir && settings.grid_data_dir),
      },
      {
        key: "import",
        title: "导入站点数据",
        done: tasks.some(
          (t) =>
            t.task_type.startsWith("DataImport") &&
            t.status === "COMPLETED"
        ),
      },
      {
        key: "process",
        title: "数据预处理",
        done: tasks.some(
          (t) =>
            t.task_type.startsWith("DataProcess") &&
            t.status === "COMPLETED"
        ),
      },
      {
        key: "train",
        title: "模型训练",
        done: tasks.some(
          (t) =>
            t.task_type.startsWith("ModelTrain") &&
            t.status === "COMPLETED"
        ),
      },
      {
        key: "correct",
        title: "数据订正",
        done: tasks.some(
          (t) =>
            t.task_type.startsWith("DataCorrect") &&
            t.status === "COMPLETED"
        ),
      },
    ];
    const doneCount = steps.filter((s) => s.done).length;
    const recentTasks = tasks.slice(0, 8);

    return (
      <>
        {/* 总览统计 */}
        <div className="stats-row">
          <div className="stat-card">
            <span>可用站点</span>
            <strong>{stations.length}</strong>
          </div>
          <div className="stat-card">
            <span>已训练模型</span>
            <strong>{models.length}</strong>
          </div>
          <div className="stat-card">
            <span>执行中</span>
            <strong>{stats.processing}</strong>
          </div>
          <div className="stat-card">
            <span>已完成任务</span>
            <strong>{stats.completed}</strong>
          </div>
          <div className="stat-card">
            <span>失败任务</span>
            <strong>{stats.failed}</strong>
          </div>
          <div className="stat-card">
            <span>工作流进度</span>
            <strong>
              {doneCount}/{steps.length}
            </strong>
          </div>
        </div>

        <div className="dashboard-grid">
          {/* 工作流 */}
          <div className="dashboard-card">
            <h3>工作流进度</h3>
            <div className="workflow-steps">
              {steps.map((s, i) => (
                <button
                  key={s.key}
                  className="workflow-step"
                  onClick={() => setModuleKey(s.key as ModuleKey)}
                  style={{ cursor: "pointer", textAlign: "left" }}
                >
                  <span className={`step-num${s.done ? " done" : ""}`}>
                    {s.done ? "✓" : i + 1}
                  </span>
                  <span style={{ flex: 1 }}>{s.title}</span>
                  <StatusPill status={s.done ? "COMPLETED" : "IDLE"} />
                </button>
              ))}
            </div>
          </div>

          {/* 最近任务 */}
          <div className="dashboard-card" style={{ gridColumn: "span 2" }}>
            <div className="card-header">
              <h2>最近任务</h2>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setModuleKey("tasks")}
              >
                查看全部
              </button>
            </div>
            {recentTasks.length > 0 ? (
              <div className="task-list">
                {recentTasks.map((t) => (
                  <div key={t.task_id} className="task-item">
                    <div className="task-top">
                      <strong>{t.task_name}</strong>
                      <StatusPill status={t.status} />
                    </div>
                    <div className="task-meta">
                      <span>{t.task_type}</span>
                      <span>{t.progress}%</span>
                    </div>
                    <ProgressBar value={t.progress} slim />
                  </div>
                ))}
              </div>
            ) : (
              <Empty>暂无任务，从左侧导航开始操作</Empty>
            )}
          </div>
        </div>

        {/* 快捷入口 */}
        <div className="card">
          <div className="card-header">
            <h2>快捷操作</h2>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              className="btn btn-ghost"
              onClick={() => setModuleKey("settings")}
            >
              配置数据源
            </button>
            <button
              className="btn btn-ghost"
              onClick={() => setModuleKey("train")}
            >
              开始训练
            </button>
            <button
              className="btn btn-ghost"
              onClick={() => setModuleKey("pivot")}
            >
              数据透视
            </button>
            <button
              className="btn btn-ghost"
              onClick={() => setModuleKey("multieval")}
            >
              多站点评估
            </button>
          </div>
        </div>
      </>
    );
  }

  function renderSettings(): ReactNode {
    return (
      <div className="card">
        <div className="card-header">
          <h2>数据源路径</h2>
          <button
            className="btn btn-primary"
            disabled={busy === "save-settings"}
            onClick={() => void saveSettings()}
          >
            {busy === "save-settings" ? "保存中..." : "保存配置"}
          </button>
        </div>
        <div className="field-grid cols-2">
          {(
            Object.entries(settings) as Array<[string, string]>
          ).map(([key, value]) => (
            <div className="field" key={key}>
              <label>{key}</label>
              <input
                value={value}
                onChange={(e) =>
                  setSettings((c) => ({ ...c, [key]: e.target.value }))
                }
              />
            </div>
          ))}
        </div>
      </div>
    );
  }

  function renderImport(): ReactNode {
    return (
      <>
        <div className="card">
          <div className="card-header">
            <h2>导入准备</h2>
            <div className="card-actions">
              <button
                className="btn btn-ghost"
                disabled={busy === "check-import"}
                onClick={() => void checkImportFiles()}
              >
                {busy === "check-import" ? "检查中..." : "检查文件"}
              </button>
              <button
                className="btn btn-primary"
                disabled={busy === "start-import"}
                onClick={() => void startImport()}
              >
                {busy === "start-import" ? "启动中..." : "开始导入"}
              </button>
            </div>
          </div>
          <div className="stats-row">
            <div className="stat-card">
              <span>待导入文件</span>
              <strong>{importCount}</strong>
            </div>
            <div className="stat-card">
              <span>已显示</span>
              <strong>
                {Math.min(importFiles.length, 12)} / {importFiles.length}
              </strong>
            </div>
          </div>
        </div>

        {/* 文件列表 */}
        {importFiles.length > 0 ? (
          <div className="card">
            <div className="card-header">
              <h2>文件列表</h2>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {importFiles.slice(0, 12).map((f) => (
                <div
                  key={f}
                  style={{
                    padding: "8px 12px",
                    borderRadius: "var(--radius-sm)",
                    background: "rgba(255,255,255,0.02)",
                    border: "1px solid var(--border)",
                    fontSize: "0.82rem",
                    fontFamily: "var(--font-mono)",
                    wordBreak: "break-all",
                  }}
                >
                  {f}
                </div>
              ))}
              {importFiles.length > 12 && (
                <div style={{ color: "var(--text-dim)", fontSize: "0.8rem", padding: "4px 12px" }}>
                  ... 还有 {importFiles.length - 12} 个文件
                </div>
              )}
            </div>
          </div>
        ) : (
          <Empty>
            先点击"检查文件"确认待导入文件数量和来源路径
          </Empty>
        )}
      </>
    );
  }

  function renderProcess(): ReactNode {
    return (
      <div className="card">
        <div className="card-header">
          <h2>预处理配置</h2>
          <button
            className="btn btn-primary"
            disabled={
              busy === "start-process" ||
              processForm.elements.length === 0
            }
            onClick={() => void startProcess()}
          >
            {busy === "start-process" ? "提交中..." : "开始预处理"}
          </button>
        </div>

        {/* 要素选择 */}
        <div style={{ marginBottom: 14 }}>
          <label style={{ fontSize: "0.8rem", color: "var(--text-dim)", display: "block", marginBottom: 8 }}>
            气象要素（可多选）
          </label>
          <div className="chip-row">
            {ELEMENTS.map((el) => (
              <button
                key={el}
                className={`chip${processForm.elements.includes(el) ? " selected" : ""}`}
                onClick={() => toggleProcessElement(el)}
              >
                {el}
              </button>
            ))}
          </div>
        </div>

        {/* 参数表单 */}
        <div className="field-grid cols-3">
          <div className="field">
            <label>开始年份</label>
            <input
              value={processForm.start_year}
              onChange={(e) =>
                setProcessForm((c) => ({
                  ...c,
                  start_year: e.target.value,
                }))
              }
            />
          </div>
          <div className="field">
            <label>结束年份</label>
            <input
              value={processForm.end_year}
              onChange={(e) =>
                setProcessForm((c) => ({
                  ...c,
                  end_year: e.target.value,
                }))
              }
            />
          </div>
          <div className="field">
            <label>工作进程数</label>
            <input
              value={processForm.num_workers}
              onChange={(e) =>
                setProcessForm((c) => ({
                  ...c,
                  num_workers: e.target.value,
                }))
              }
            />
          </div>
        </div>
      </div>
    );
  }

  /* 训练子面板：参数配置 */
  function renderTrainConfig(): ReactNode {
    const entries = Object.entries(modelConfig);
    return (
      <div className="card">
        <div className="card-header">
          <h2>超参数配置</h2>
          <div className="card-actions">
            <select
              value={configModel}
              onChange={(e) => setConfigModel(e.target.value)}
              style={{ width: 130 }}
            >
              <option value="XGBoost">XGBoost</option>
              <option value="LightGBM">LightGBM</option>
            </select>
            <select
              value={configElement}
              onChange={(e) => setConfigElement(e.target.value)}
              style={{ width: 140 }}
            >
              {ELEMENTS.map((el) => (
                <option key={el} value={el}>{el}</option>
              ))}
            </select>
            <button
              className="btn btn-ghost btn-sm"
              disabled={busy === "fetch-config"}
              onClick={() => void fetchModelConfig()}
            >
              {busy === "fetch-config" ? "加载中..." : "加载配置"}
            </button>
            {entries.length > 0 && (
              <button
                className="btn btn-primary btn-sm"
                disabled={busy === "update-config"}
                onClick={() => void updateModelConfig()}
              >
                {busy === "update-config" ? "保存中..." : "更新配置"}
              </button>
            )}
          </div>
        </div>
        {entries.length > 0 ? (
          <div className="config-grid">
            {entries.map(([key, val]) => (
              <div className="config-field" key={key}>
                <label>{key}</label>
                <input
                  value={String(val)}
                  onChange={(e) => {
                    let parsed: unknown = e.target.value;
                    if (!Number.isNaN(Number(parsed))) parsed = Number(parsed);
                    setModelConfig((c) => ({ ...c, [key]: parsed }));
                  }}
                />
              </div>
            ))}
          </div>
        ) : (
          <Empty>
            选择模型和要素后点击"加载配置"查看超参数
          </Empty>
        )}
      </div>
    );
  }

  /* 训练子面板：训练表单 */
  function renderTrainForm(): ReactNode {
    return (
      <div className="card">
        <div className="card-header">
          <h2>训练配置</h2>
          <button
            className="btn btn-primary"
            disabled={
              busy === "start-train" || trainForm.element.length === 0
            }
            onClick={() => void startTrain()}
          >
            {busy === "start-train" ? "提交中..." : "开始训练"}
          </button>
        </div>

        {/* 要素选择 */}
        <div style={{ marginBottom: 14 }}>
          <label style={{ fontSize: "0.8rem", color: "var(--text-dim)", display: "block", marginBottom: 8 }}>
            训练要素（可多选）
          </label>
          <div className="chip-row">
            {ELEMENTS.map((el) => (
              <button
                key={el}
                className={`chip${trainForm.element.includes(el) ? " selected" : ""}`}
                onClick={() => toggleTrainElement(el)}
              >
                {el}
              </button>
            ))}
          </div>
        </div>

        <div className="field-grid cols-3">
          <div className="field">
            <label>开始年份</label>
            <input
              value={trainForm.start_year}
              onChange={(e) =>
                setTrainForm((c) => ({ ...c, start_year: e.target.value }))
              }
            />
          </div>
          <div className="field">
            <label>结束年份</label>
            <input
              value={trainForm.end_year}
              onChange={(e) =>
                setTrainForm((c) => ({ ...c, end_year: e.target.value }))
              }
            />
          </div>
          <div className="field">
            <label>提前停止轮数</label>
            <input
              value={trainForm.early_stopping_rounds}
              onChange={(e) =>
                setTrainForm((c) => ({
                  ...c,
                  early_stopping_rounds: e.target.value,
                }))
              }
            />
          </div>
        </div>
        <div className="field-grid cols-2" style={{ marginTop: 12 }}>
          <div className="field">
            <label>季节</label>
            <select
              value={trainForm.season}
              onChange={(e) =>
                setTrainForm((c) => ({ ...c, season: e.target.value }))
              }
            >
              {SEASONS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>模型</label>
            <select
              value={trainForm.model}
              onChange={(e) =>
                setTrainForm((c) => ({ ...c, model: e.target.value }))
              }
            >
              <option value="XGBoost">XGBoost</option>
              <option value="LightGBM">LightGBM</option>
            </select>
          </div>
        </div>
        <div className="field" style={{ marginTop: 12 }}>
          <label>测试集取值（逗号分隔年份）</label>
          <textarea
            rows={3}
            value={trainForm.test_set_values}
            onChange={(e) =>
              setTrainForm((c) => ({
                ...c,
                test_set_values: e.target.value,
              }))
            }
            placeholder="例如：2022,2023"
          />
        </div>
      </div>
    );
  }

  /* 训练子面板：损失曲线 */
  function renderTrainLosses(): ReactNode {
    const canFetch =
      taskDetail.parent.status === "COMPLETED" &&
      !!taskDetail.parent.task_id;
    return (
      <div className="card">
        <div className="card-header">
          <h2>损失曲线</h2>
          <button
            className="btn btn-ghost btn-sm"
            disabled={!canFetch || busy === "fetch-losses"}
            onClick={() => void fetchLosses()}
          >
            {busy === "fetch-losses" ? "加载中..." : "加载损失曲线"}
          </button>
        </div>
        {lossesData && lossesData.epochs.length > 0 ? (
          <LineChart
            labels={lossesData.epochs.map(String)}
            series={[
              { name: "训练损失", color: "#00c9db", values: lossesData.train_losses },
              { name: "验证损失", color: "#fbbf24", values: lossesData.test_losses },
            ]}
          />
        ) : (
          <Empty>
            {canFetch
              ? `点击「加载损失曲线」查看训练过程`
              : "需要先选中一个已完成的训练任务"}
          </Empty>
        )}
      </div>
    );
  }

  /* 训练子面板：评估指标 */
  function renderTrainMetrics(): ReactNode {
    const canFetch =
      taskDetail.parent.status === "COMPLETED" &&
      !!taskDetail.parent.task_id;
    return (
      <div className="card">
        <div className="card-header">
          <h2>测试集评估指标</h2>
          <button
            className="btn btn-ghost btn-sm"
            disabled={!canFetch || busy === "fetch-metrics"}
            onClick={() => void fetchMetrics()}
          >
            {busy === "fetch-metrics" ? "加载中..." : "加载指标"}
          </button>
        </div>
        {metricsData ? (
          <table className="metrics-table">
            <thead>
              <tr>
                <th>指标</th>
                <th>测试集真值</th>
                <th>测试集预测</th>
              </tr>
            </thead>
            <tbody>
              {METRIC_NAMES.map((name) => (
                <tr key={name}>
                  <td style={{ fontWeight: 600 }}>{name}</td>
                  <td>{fmt(metricsData.testset_true[name])}</td>
                  <td>{fmt(metricsData.testset_pred[name])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty>
            {canFetch
              ? `点击「加载指标」查看模型评估结果`
              : "需要先选中一个已完成的训练任务"}
          </Empty>
        )}
      </div>
    );
  }

  /* 训练子面板：模型记录管理 */
  function renderModelRecords(): ReactNode {
    const completedTrainTasks = tasks.filter(
      (t) =>
        t.task_type.startsWith("ModelTrain") &&
        t.status === "COMPLETED"
    );
    return (
      <div className="card">
        <div className="card-header">
          <h2>模型记录管理</h2>
        </div>
        {/* 已保存的模型 */}
        {models.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <label style={{ fontSize: "0.8rem", color: "var(--text-dim)", display: "block", marginBottom: 8 }}>
              已保存模型（{models.length}）
            </label>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {models.map((m) => (
                <div
                  key={m.task_id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "10px 14px",
                    borderRadius: "var(--radius-sm)",
                    background: "rgba(255,255,255,0.02)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div>
                    <strong style={{ fontSize: "0.88rem" }}>{m.model_name}</strong>
                    <span style={{ color: "var(--text-dim)", fontSize: "0.78rem", marginLeft: 8 }}>
                      {m.element}
                    </span>
                  </div>
                  <button
                    className="btn btn-danger btn-sm"
                    disabled={busy === "delete-model"}
                    onClick={() => void deleteModelRecord(m.task_id)}
                  >
                    删除
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
        {/* 可保存的训练任务 */}
        {completedTrainTasks.length > 0 && (
          <div>
            <label style={{ fontSize: "0.8rem", color: "var(--text-dim)", display: "block", marginBottom: 8 }}>
              可保存的训练任务
            </label>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {completedTrainTasks
                .filter((t) => !models.some((m) => m.task_id === t.task_id))
                .slice(0, 8)
                .map((t) => (
                  <div
                    key={t.task_id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "10px 14px",
                      borderRadius: "var(--radius-sm)",
                      background: "rgba(52, 211, 153, 0.05)",
                      border: "1px solid rgba(52, 211, 153, 0.15)",
                    }}
                  >
                    <div>
                      <strong style={{ fontSize: "0.85rem" }}>{t.task_name}</strong>
                      <span style={{ color: "var(--text-dim)", fontSize: "0.75rem", marginLeft: 8 }}>
                        {t.task_id.slice(0, 8)}
                      </span>
                    </div>
                    <button
                      className="btn btn-primary btn-sm"
                      disabled={busy === "save-model"}
                      onClick={() => void saveModelRecord(t.task_id)}
                    >
                      保存为模型
                    </button>
                  </div>
                ))}
            </div>
          </div>
        )}
        {models.length === 0 && completedTrainTasks.length === 0 && (
          <Empty>
            完成训练后可在此保存模型记录，用于后续订正和评估
          </Empty>
        )}
      </div>
    );
  }

  function renderTrain(): ReactNode {
    return (
      <>
        {renderTrainConfig()}
        {renderTrainForm()}
        {renderTrainLosses()}
        {renderTrainMetrics()}
        {renderModelRecords()}
      </>
    );
  }

  async function refreshModels() {
    await runAction("refresh-models", async () => {
      const r = await api<{ models?: ModelRecord[] }>(
        "/data-correct/get-models"
      );
      const next = r.models ?? [];
      setModels(next);
      if (next[0]) {
        setCorrectForm((c) => ({
          ...c,
          model_path: c.model_path || next[0].model_path,
          element: c.element || next[0].element,
        }));
      }
      addLog("模型已同步", `当前可用 ${next.length} 个模型`, "success");
    });
  }

  async function startCorrect() {
    await runAction("start-correct", async () => {
      const r = await api<{ task_id: string; message: string }>(
        "/data-correct/start",
        {
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
        }
      );
      setSelectedTaskId(r.task_id);
      addLog("订正已启动", r.message, "success");
    });
  }

  function renderCorrect(): ReactNode {
    return (
      <>
        <div className="card">
          <div className="card-header">
            <h2>订正配置</h2>
            <div className="card-actions">
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy === "refresh-models"}
                onClick={() => void refreshModels()}
              >
                {busy === "refresh-models" ? "同步中..." : "同步模型"}
              </button>
              <button
                className="btn btn-primary"
                disabled={busy === "start-correct"}
                onClick={() => void startCorrect()}
              >
                {busy === "start-correct" ? "提交中..." : "开始订正"}
              </button>
            </div>
          </div>

          <div className="field-grid cols-2">
            <div className="field">
              <label>已保存模型</label>
              <select
                value={correctForm.model_path}
                onChange={(e) => {
                  const found = models.find(
                    (m) => m.model_path === e.target.value
                  );
                  setCorrectForm((c) => ({
                    ...c,
                    model_path: e.target.value,
                    element: found?.element ?? c.element,
                  }));
                }}
              >
                {models.map((m) => (
                  <option key={m.model_path} value={m.model_path}>
                    {m.model_name} ({m.element})
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>气象要素</label>
              <select
                value={correctForm.element}
                onChange={(e) =>
                  setCorrectForm((c) => ({
                    ...c,
                    element: e.target.value,
                  }))
                }
              >
                {ELEMENTS.map((el) => (
                  <option key={el} value={el}>{el}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="field-grid cols-4" style={{ marginTop: 12 }}>
            <div className="field">
              <label>开始年份</label>
              <input
                value={correctForm.start_year}
                onChange={(e) =>
                  setCorrectForm((c) => ({
                    ...c,
                    start_year: e.target.value,
                  }))
                }
              />
            </div>
            <div className="field">
              <label>结束年份</label>
              <input
                value={correctForm.end_year}
                onChange={(e) =>
                  setCorrectForm((c) => ({
                    ...c,
                    end_year: e.target.value,
                  }))
                }
              />
            </div>
            <div className="field">
              <label>块大小</label>
              <input
                value={correctForm.block_size}
                onChange={(e) =>
                  setCorrectForm((c) => ({
                    ...c,
                    block_size: e.target.value,
                  }))
                }
              />
            </div>
            <div className="field">
              <label>进程数</label>
              <input
                value={correctForm.num_workers}
                onChange={(e) =>
                  setCorrectForm((c) => ({
                    ...c,
                    num_workers: e.target.value,
                  }))
                }
              />
            </div>
          </div>
        </div>

        {/* 选中模型信息 */}
        {selectedModel ? (
          <div className="highlight-row">
            <div className="highlight-item">
              <span>模型</span>
              <strong>{selectedModel.model_name}</strong>
            </div>
            <div className="highlight-item">
              <span>关联任务</span>
              <strong>{selectedModel.task_id.slice(0, 12)}...</strong>
            </div>
            <div className="highlight-item">
              <span>要素</span>
              <strong>{selectedModel.element}</strong>
            </div>
          </div>
        ) : (
          <Empty>
            当前没有可用模型，请先在"模型训练"模块中训练并保存模型
          </Empty>
        )}
      </>
    );
  }

  /* ===== 透视 API 操作 ===== */

  async function loadRawStation(form = pivotForm) {
    await runAction("raw-station", async () => {
      const r = await api<RawStationData>("/data-preview/station-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          station_name: form.station_name,
          element: form.element,
          start_time: toApiDateTime(form.start_time),
          end_time: toApiDateTime(form.end_time),
        }),
      });
      setRawStationData(r);
      addLog(
        "站点曲线已加载",
        `${r.timestamps.length} 个时刻`,
        "success"
      );
    });
  }

  async function loadRawHeatmap(form = pivotForm) {
    await runAction("raw-grid", async () => {
      const r = await api<RawGridHeatmapData>("/data-preview/grid-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          element: form.element,
          timestamp: toApiDateTime(form.heatmap_time),
        }),
      });
      setRawGridData(r);
      const ri = Math.floor(r.lats.length / 2);
      const ci = Math.floor(r.lons.length / 2);
      setPivotForm((c) => ({
        ...c,
        lat: String(r.lats[ri] ?? c.lat),
        lon: String(r.lons[ci] ?? c.lon),
      }));
      addLog(
        "原始热力图已加载",
        `${r.lats.length} × ${r.lons.length}`,
        "success"
      );
    });
  }

  async function startRawGridSeries(form = pivotForm) {
    await runAction("raw-series", async () => {
      const lat = Number(form.lat);
      const lon = Number(form.lon);
      if (Number.isNaN(lat) || Number.isNaN(lon))
        throw new Error("请先输入有效经纬度");
      const r = await api<{ task_id: string; message: string }>(
        "/data-preview/grid-time-series",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            element: form.element,
            lat,
            lon,
            start_time: toApiDateTime(form.start_time),
            end_time: toApiDateTime(form.end_time),
          }),
        }
      );
      setRawGridTaskId(r.task_id);
      setRawGridSeriesData(null);
      addLog("格点时序已提交", r.message, "success");
    });
  }

  async function loadProcessed(form = pivotForm) {
    await runAction("pivot-processed", async () => {
      const r = await api<PivotProcessedData>(
        "/data-pivot/processed-data",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            station_name: form.station_name,
            element: form.element,
            start_time: toApiDateTime(form.start_time),
            end_time: toApiDateTime(form.end_time),
          }),
        }
      );
      setProcessedData(r);
      addLog(
        "站点对比已加载",
        `${r.timestamps.length} 个时刻`,
        "success"
      );
    });
  }

  async function loadPivotHeatmap(form = pivotForm) {
    await runAction("pivot-heatmap", async () => {
      const r = await api<PivotHeatmapData>("/data-pivot/grid-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          element: form.element,
          timestamp: toApiDateTime(form.heatmap_time),
        }),
      });
      setHeatmapData(r);
      const focus = {
        row: Math.floor(r.lats.length / 2),
        col: Math.floor(r.lons.length / 2),
      };
      setHeatmapFocus(focus);
      setPivotForm((c) => ({
        ...c,
        lat: String(r.lats[focus.row] ?? ""),
        lon: String(r.lons[focus.col] ?? ""),
      }));
      addLog(
        "订正热力图已加载",
        `${r.lats.length} × ${r.lons.length}`,
        "success"
      );
    });
  }

  async function startPivotSeries(form = pivotForm) {
    await runAction("pivot-series", async () => {
      const lat = Number(form.lat);
      const lon = Number(form.lon);
      if (Number.isNaN(lat) || Number.isNaN(lon))
        throw new Error("请先输入有效经纬度");
      const r = await api<{ task_id: string; message: string }>(
        "/data-pivot/grid-data-timeseries",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            element: form.element,
            lat,
            lon,
            start_time: toApiDateTime(form.start_time),
            end_time: toApiDateTime(form.end_time),
          }),
        }
      );
      setPivotSeriesTaskId(r.task_id);
      setPivotSeriesData(null);
      addLog("订正时序已提交", r.message, "success");
    });
  }

  async function startModelEval() {
    await runAction("model-eval", async () => {
      const r = await api<{ task_id: string; message: string }>(
        "/data-pivot/model-evaluation",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model_paths: models.map((m) => m.model_path),
            element: pivotForm.element,
            station_name: pivotForm.station_name,
            start_time: toApiDateTime(pivotForm.start_time),
            end_time: toApiDateTime(pivotForm.end_time),
          }),
        }
      );
      setModelEvalTaskId(r.task_id);
      setModelEvalResult(null);
      addLog("模型评估已提交", r.message, "success");
    });
  }

  async function startModelRank() {
    await runAction("model-rank", async () => {
      const r = await api<{ task_id: string; message: string }>(
        "/data-pivot/model-ranking",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            element: pivotForm.element,
            season: "全年",
            test_set_values: ["2022", "2023"],
          }),
        }
      );
      setRankTaskId(r.task_id);
      setRankResult(null);
      addLog("模型排名已提交", r.message, "success");
    });
  }

  async function startExportGrid(type: "data" | "image") {
    const endpoint =
      type === "data"
        ? "/data-preview/export-grid-data"
        : "/data-preview/export-grid-images";
    await runAction("export-grid", async () => {
      const r = await api<{ task_id: string; message: string }>(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          element: pivotForm.element,
          start_time: toApiDateTime(pivotForm.start_time),
          end_time: toApiDateTime(pivotForm.end_time),
        }),
      });
      setExportTaskId(r.task_id);
      setExportSource("preview");
      setExportStatus(null);
      addLog(
        "导出任务已提交",
        r.message,
        "success"
      );
    });
  }

  async function startExportCorrected(type: "data" | "image") {
    const endpoint =
      type === "data"
        ? "/data-pivot/export-corrected-data"
        : "/data-pivot/export-corrected-images";
    await runAction("export-corrected", async () => {
      const r = await api<{ task_id: string; message: string }>(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          element: pivotForm.element,
          start_time: toApiDateTime(pivotForm.start_time),
          end_time: toApiDateTime(pivotForm.end_time),
        }),
      });
      setExportTaskId(r.task_id);
      setExportSource("pivot");
      setExportStatus(null);
      addLog("订正导出已提交", r.message, "success");
    });
  }

  /* 透视轮询 Effects */

  useEffect(() => {
    if (!rawGridTaskId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await api<{
          status: string;
          progress: number;
          result?: RawGridTimeseriesData | null;
          error?: string | null;
        }>(`/data-preview/grid-time-series/status/${rawGridTaskId}`);
        if (cancelled) return;
        if (r.status === "COMPLETED" && r.result)
          setRawGridSeriesData(r.result);
        if (r.status === "COMPLETED" || r.status === "FAILED")
          setRawGridTaskId("");
      } catch { /* 静默 */ }
    };
    void poll();
    const timer = setInterval(() => void poll(), 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [rawGridTaskId]);

  useEffect(() => {
    if (!pivotSeriesTaskId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await api<{
          status: string;
          progress: number;
          progress_text: string;
          results?: PivotTimeseriesData | null;
        }>(`/data-pivot/grid-data-timeseries/status/${pivotSeriesTaskId}`);
        if (cancelled) return;
        if (r.status === "COMPLETED" && r.results)
          setPivotSeriesData(r.results);
        if (r.status === "COMPLETED" || r.status === "FAILED")
          setPivotSeriesTaskId("");
      } catch { /* 静默 */ }
    };
    void poll();
    const timer = setInterval(() => void poll(), 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [pivotSeriesTaskId]);

  useEffect(() => {
    if (!modelEvalTaskId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await api<{
          status: string;
          progress: number;
          results?: ModelEvalResult | null;
        }>(`/data-pivot/model-evaluation/status/${modelEvalTaskId}`);
        if (cancelled) return;
        if (r.status === "COMPLETED" && r.results)
          setModelEvalResult(r.results);
        if (r.status === "COMPLETED" || r.status === "FAILED")
          setModelEvalTaskId("");
      } catch { /* 静默 */ }
    };
    void poll();
    const timer = setInterval(() => void poll(), 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [modelEvalTaskId]);

  useEffect(() => {
    if (!rankTaskId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await api<{
          status: string;
          progress: number;
          results?: ModelRankResult | null;
        }>(`/data-pivot/model-ranking/status/${rankTaskId}`);
        if (cancelled) return;
        if (r.status === "COMPLETED" && r.results) setRankResult(r.results);
        if (r.status === "COMPLETED" || r.status === "FAILED")
          setRankTaskId("");
      } catch { /* 静默 */ }
    };
    void poll();
    const timer = setInterval(() => void poll(), 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [rankTaskId]);

  useEffect(() => {
    if (!exportTaskId) return;
    const statusUrl = exportSource === "preview"
      ? `/data-preview/export-grid-data/status/${exportTaskId}`
      : `/data-pivot/export-corrected-data/status/${exportTaskId}`;
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await api<ExportStatus>(statusUrl);
        if (cancelled) return;
        setExportStatus(r);
        if (r.status === "COMPLETED" || r.status === "FAILED")
          setExportTaskId("");
      } catch { /* 静默 */ }
    };
    void poll();
    const timer = setInterval(() => void poll(), 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [exportTaskId, exportSource]);

  function selectHeatCell(row: number, col: number) {
    setHeatmapFocus({ row, col });
    const src = heatmapData ?? rawGridData;
    if (!src) return;
    setPivotForm((c) => ({
      ...c,
      lat: String(src.lats[row] ?? ""),
      lon: String(src.lons[col] ?? ""),
    }));
  }

  function applyQuickRange(hours: number) {
    const next = shiftHours(pivotForm.end_time, hours);
    if (!next.start || !next.end) return;
    setPivotForm((c) => ({ ...c, start_time: next.start, end_time: next.end }));
    addLog(
      "快捷范围",
      `已切换为最近 ${hours >= 24 ? `${hours / 24} 天` : `${hours} 小时`}`,
      "info"
    );
  }

  /* ===== 透视子面板 ===== */

  function renderPivot(): ReactNode {
    const rangeLabel = `${formatAxisTick(toApiDateTime(pivotForm.start_time))} → ${formatAxisTick(toApiDateTime(pivotForm.end_time))}`;
    const heatLabel = formatAxisTick(toApiDateTime(pivotForm.heatmap_time));

    const processedSummary = processedData
      ? {
          stationMean: average(processedData.station_values),
          gridMean: average(processedData.grid_values),
          bias: diffAverage(processedData.station_values, processedData.grid_values),
          count: processedData.timestamps.length,
        }
      : null;

    const focusMeta = heatmapData && heatmapFocus
      ? {
          lat: heatmapData.lats[heatmapFocus.row],
          lon: heatmapData.lons[heatmapFocus.col],
          before: heatmapData.values_before[heatmapFocus.row]?.[heatmapFocus.col] ?? null,
          after: heatmapData.values_after[heatmapFocus.row]?.[heatmapFocus.col] ?? null,
        }
      : null;

    return (
      <>
        {/* 筛选工具栏 */}
        <div className="pivot-toolbar">
          <div className="card-header" style={{ marginBottom: 12 }}>
            <h2>分析筛选</h2>
          </div>
          <div className="field-grid cols-3">
            <div className="field">
              <label>站点</label>
              <select
                value={pivotForm.station_name}
                onChange={(e) =>
                  setPivotForm((c) => ({ ...c, station_name: e.target.value }))
                }
              >
                {stations.map((s) => (
                  <option key={s.name} value={s.name}>{s.name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>要素</label>
              <select
                value={pivotForm.element}
                onChange={(e) =>
                  setPivotForm((c) => ({ ...c, element: e.target.value }))
                }
              >
                {ELEMENTS.map((el) => (
                  <option key={el} value={el}>{el}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>热力图时刻</label>
              <input
                type="datetime-local"
                value={pivotForm.heatmap_time}
                onChange={(e) =>
                  setPivotForm((c) => ({ ...c, heatmap_time: e.target.value }))
                }
              />
            </div>
          </div>
          <div className="quick-range-row" style={{ marginTop: 10 }}>
            <span className="quick-range-label">快捷范围</span>
            <button className="chip" onClick={() => applyQuickRange(24)}>
              24小时
            </button>
            <button className="chip" onClick={() => applyQuickRange(72)}>
              3天
            </button>
            <button className="chip" onClick={() => applyQuickRange(168)}>
              7天
            </button>
          </div>
          <div className="field-grid cols-4" style={{ marginTop: 10 }}>
            <div className="field">
              <label>开始时间</label>
              <input
                type="datetime-local"
                value={pivotForm.start_time}
                onChange={(e) =>
                  setPivotForm((c) => ({ ...c, start_time: e.target.value }))
                }
              />
            </div>
            <div className="field">
              <label>结束时间</label>
              <input
                type="datetime-local"
                value={pivotForm.end_time}
                onChange={(e) =>
                  setPivotForm((c) => ({ ...c, end_time: e.target.value }))
                }
              />
            </div>
            <div className="field">
              <label>纬度</label>
              <input
                value={pivotForm.lat}
                onChange={(e) =>
                  setPivotForm((c) => ({ ...c, lat: e.target.value }))
                }
                placeholder="点击热力图自动填入"
              />
            </div>
            <div className="field">
              <label>经度</label>
              <input
                value={pivotForm.lon}
                onChange={(e) =>
                  setPivotForm((c) => ({ ...c, lon: e.target.value }))
                }
                placeholder="点击热力图自动填入"
              />
            </div>
          </div>
        </div>

        {/* 统计摘要 */}
        <div className="stats-row">
          <div className="stat-card">
            <span>原始站点均值</span>
            <strong>{fmt(rawStationData ? average(rawStationData.values) : null)}</strong>
          </div>
          <div className="stat-card">
            <span>对比站点均值</span>
            <strong>{fmt(processedSummary?.stationMean)}</strong>
          </div>
          <div className="stat-card">
            <span>对比格点均值</span>
            <strong>{fmt(processedSummary?.gridMean)}</strong>
          </div>
          <div className="stat-card">
            <span>平均偏差</span>
            <strong>{fmt(processedSummary?.bias)}</strong>
          </div>
        </div>

        {/* 双栏：原始预览 + 订正对比 */}
        <div className="pivot-columns">
          {/* 原始预览 */}
          <div className="pivot-col">
            <h3>原始预览</h3>
            <p>训练前检查站点观测和原始格点分布</p>
            <div className="pivot-status-row">
              <span className={`pivot-pill${rawStationData ? " active" : ""}`}>
                站点曲线 {rawStationData ? "已就绪" : "未加载"}
              </span>
              <span className={`pivot-pill${rawGridData ? " active" : ""}`}>
                格点热力图 {rawGridData ? "已就绪" : "未加载"}
              </span>
              <span className={`pivot-pill${rawGridSeriesData ? " active" : ""}`}>
                格点时序 {rawGridSeriesData ? "已就绪" : "未加载"}
              </span>
            </div>
            <div className="pivot-actions">
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy === "raw-station"}
                onClick={() => void loadRawStation()}
              >
                {busy === "raw-station" ? "查询中..." : "站点曲线"}
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy === "raw-grid"}
                onClick={() => void loadRawHeatmap()}
              >
                {busy === "raw-grid" ? "加载中..." : "格点热力图"}
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy === "raw-series" || !!rawGridTaskId}
                onClick={() => void startRawGridSeries()}
              >
                {busy === "raw-series" ? "提交中..." : rawGridTaskId ? "提取中..." : "格点时序"}
              </button>
            </div>
            {/* 原始站点曲线 */}
            {rawStationData && rawStationData.timestamps.length > 0 && (
              <LineChart
                labels={rawStationData.timestamps}
                series={[
                  { name: rawStationData.station_name, color: "#00c9db", values: rawStationData.values },
                ]}
              />
            )}
            {/* 原始格点热力图 */}
            {rawGridData && (
              <HeatmapMatrix
                title="原始格点热力图"
                subtitle={`时刻 ${heatLabel}`}
                values={rawGridData.values}
                lats={rawGridData.lats}
                lons={rawGridData.lons}
                focus={heatmapFocus}
                onSelect={selectHeatCell}
              />
            )}
            {/* 原始格点时序 */}
            {rawGridSeriesData && rawGridSeriesData.timestamps.length > 0 && (
              <LineChart
                labels={rawGridSeriesData.timestamps}
                series={[
                  {
                    name: `格点 (${fmt(rawGridSeriesData.lat, 3)}, ${fmt(rawGridSeriesData.lon, 3)})`,
                    color: "#fbbf24",
                    values: rawGridSeriesData.values,
                  },
                ]}
              />
            )}
          </div>

          {/* 订正对比 */}
          <div className="pivot-col">
            <h3>订正对比</h3>
            <p>订正完成后对比站点、空间分布和时序变化</p>
            <div className="pivot-status-row">
              <span className={`pivot-pill${processedData ? " active" : ""}`}>
                站点对比 {processedData ? "已就绪" : "未加载"}
              </span>
              <span className={`pivot-pill${heatmapData ? " active" : ""}`}>
                前后热力图 {heatmapData ? "已就绪" : "未加载"}
              </span>
              <span className={`pivot-pill${pivotSeriesData ? " active" : ""}`}>
                前后时序 {pivotSeriesData ? "已就绪" : "未加载"}
              </span>
            </div>
            <div className="pivot-actions">
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy === "pivot-processed"}
                onClick={() => void loadProcessed()}
              >
                {busy === "pivot-processed" ? "查询中..." : "站点对比"}
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy === "pivot-heatmap"}
                onClick={() => void loadPivotHeatmap()}
              >
                {busy === "pivot-heatmap" ? "加载中..." : "前后热力图"}
              </button>
              <button
                className="btn btn-primary btn-sm"
                disabled={busy === "pivot-series" || !!pivotSeriesTaskId}
                onClick={() => void startPivotSeries()}
              >
                {busy === "pivot-series" ? "提交中..." : pivotSeriesTaskId ? "提取中..." : "前后时序"}
              </button>
            </div>
            {/* 站点对比 */}
            {processedData && processedData.timestamps.length > 0 && (
              <>
                <LineChart
                  labels={processedData.timestamps}
                  series={[
                    { name: "站点实测", color: "#00c9db", values: processedData.station_values },
                    { name: "原始格点", color: "#fbbf24", values: processedData.grid_values },
                  ]}
                />
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <Sparkline title="站点实测" color="#00c9db" values={processedData.station_values} />
                  <Sparkline title="原始格点" color="#fbbf24" values={processedData.grid_values} />
                </div>
              </>
            )}
            {/* 选中格点信息 */}
            {focusMeta && (
              <div className="highlight-row">
                <div className="highlight-item">
                  <span>纬度</span>
                  <strong>{fmt(focusMeta.lat, 3)}</strong>
                </div>
                <div className="highlight-item">
                  <span>经度</span>
                  <strong>{fmt(focusMeta.lon, 3)}</strong>
                </div>
                <div className="highlight-item">
                  <span>订正前</span>
                  <strong>{fmt(focusMeta.before, 3)}</strong>
                </div>
                <div className="highlight-item">
                  <span>订正后</span>
                  <strong>{fmt(focusMeta.after, 3)}</strong>
                </div>
              </div>
            )}
            {/* 订正前后热力图 */}
            {heatmapData && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <HeatmapMatrix
                  title="订正前"
                  subtitle={`时刻 ${heatLabel}`}
                  values={heatmapData.values_before}
                  lats={heatmapData.lats}
                  lons={heatmapData.lons}
                  focus={heatmapFocus}
                  onSelect={selectHeatCell}
                />
                <HeatmapMatrix
                  title="订正后"
                  subtitle={`时刻 ${heatLabel}`}
                  values={heatmapData.values_after}
                  lats={heatmapData.lats}
                  lons={heatmapData.lons}
                  focus={heatmapFocus}
                  onSelect={selectHeatCell}
                />
              </div>
            )}
            {/* 订正前后时序 */}
            {pivotSeriesData && pivotSeriesData.timestamps.length > 0 && (
              <LineChart
                labels={pivotSeriesData.timestamps}
                series={[
                  { name: "订正前", color: "#fb7185", values: pivotSeriesData.values_before },
                  { name: "订正后", color: "#34d399", values: pivotSeriesData.values_after },
                ]}
              />
            )}
          </div>
        </div>

        {/* 模型评估 */}
        <div className="card">
          <div className="card-header">
            <h2>模型评估</h2>
            <div className="card-actions">
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy === "model-eval" || !!modelEvalTaskId || models.length === 0}
                onClick={() => void startModelEval()}
              >
                {busy === "model-eval" ? "提交中..." : modelEvalTaskId ? "评估中..." : "启动评估"}
              </button>
            </div>
          </div>
          {modelEvalResult ? (
            <>
              {modelEvalResult.pred_values.length > 0 && (
                <LineChart
                  labels={modelEvalResult.timestamps}
                  series={[
                    { name: "站点实测", color: "#00c9db", values: modelEvalResult.station_values },
                    { name: "原始格点", color: "#fbbf24", values: modelEvalResult.grid_values },
                    ...modelEvalResult.pred_values.map((pv, i) => ({
                      name: pv.model_name,
                      color: ["#a78bfa", "#f472b6", "#38bdf8", "#4ade80"][i % 4],
                      values: pv.pred_values,
                    })),
                  ]}
                />
              )}
              {modelEvalResult.metrics.length > 0 && (
                <table className="metrics-table" style={{ marginTop: 12 }}>
                  <thead>
                    <tr>
                      <th>模型</th>
                      {METRIC_NAMES.map((n) => (
                        <th key={n}>{n}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {modelEvalResult.metrics.map((m, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 600 }}>{m.model_name}</td>
                        {METRIC_NAMES.map((n) => (
                          <td key={n}>{fmt(m.metrics[n])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          ) : (
            <Empty>
              {models.length > 0
                ? `点击「启动评估」对比所有模型在当前站点的预测效果`
                : "需要先在训练模块中保存模型"}
            </Empty>
          )}
        </div>

        {/* 模型排名 */}
        <div className="card">
          <div className="card-header">
            <h2>模型排名</h2>
            <div className="card-actions">
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy === "model-rank" || !!rankTaskId}
                onClick={() => void startModelRank()}
              >
                {busy === "model-rank" ? "提交中..." : rankTaskId ? "排名中..." : "启动排名"}
              </button>
            </div>
          </div>
          {rankResult && rankResult.ranked_models.length > 0 ? (
            <table className="metrics-table">
              <thead>
                <tr>
                  <th>排名</th>
                  <th>模型</th>
                  <th>季节</th>
                  {METRIC_NAMES.map((n) => (
                    <th key={n}>{n}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rankResult.ranked_models.slice(0, 20).map((m, i) => (
                  <tr key={m.model_id}>
                    <td style={{ fontWeight: 700 }}>#{i + 1}</td>
                    <td>{m.model_name}</td>
                    <td>{m.season}</td>
                    {METRIC_NAMES.map((n) => (
                      <td key={n}>{fmt(m.metrics[n])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>
              {rankTaskId ? "正在排名中..." : `点击「启动排名」对所有模型按指标排序`}
            </Empty>
          )}
        </div>

        {/* 数据导出 */}
        <div className="export-row">
          <div className="export-card">
            <h3>原始网格数据导出</h3>
            <p>导出指定要素和时间范围的原始格点数据</p>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy === "export-grid"}
                onClick={() => void startExportGrid("data")}
              >
                导出 NetCDF
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy === "export-grid"}
                onClick={() => void startExportGrid("image")}
              >
                导出 PNG
              </button>
            </div>
          </div>
          <div className="export-card">
            <h3>订正后数据导出</h3>
            <p>导出订正后的格点数据或可视化图片</p>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy === "export-corrected"}
                onClick={() => void startExportCorrected("data")}
              >
                导出 NetCDF
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy === "export-corrected"}
                onClick={() => void startExportCorrected("image")}
              >
                导出 PNG
              </button>
            </div>
          </div>
        </div>
        {/* 导出状态 */}
        {exportStatus && (
          <div className="card">
            <div className="card-header">
              <h2>导出任务</h2>
              <StatusPill status={exportStatus.status} />
            </div>
            <ProgressBar value={exportStatus.progress} />
            <p style={{ color: "var(--text-dim)", fontSize: "0.82rem", marginTop: 8 }}>
              {exportStatus.progress_text || `${exportStatus.progress}%`}
            </p>
            {exportStatus.download_url && (
              <a
                href={`${baseUrl.replace(/\/$/, "")}${exportStatus.download_url}`}
                style={{
                  display: "inline-block",
                  marginTop: 10,
                  color: "var(--accent)",
                  fontWeight: 600,
                  fontSize: "0.9rem",
                }}
              >
                点击下载
              </a>
            )}
          </div>
        )}
      </>
    );
  }

  /* ===== 多站点评估 ===== */

  async function startMultiEval() {
    await runAction("multi-eval", async () => {
      const r = await api<{ task_id: string; message: string }>(
        "/model-train/multi-station-eval/start",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model_name: multiEvalForm.model_name,
            element: multiEvalForm.element,
            model_file: multiEvalForm.model_file,
            start_year: Number(multiEvalForm.start_year),
            end_year: Number(multiEvalForm.end_year),
            season: multiEvalForm.season,
          }),
        }
      );
      setMultiEvalTaskId(r.task_id);
      setMultiEvalResult(null);
      addLog("多站点评估已启动", r.message, "success");
    });
  }

  useEffect(() => {
    if (!multiEvalTaskId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await api<{
          status: string;
          progress: number;
          progress_text: string;
          results?: {
            results?: StationEvalResult[];
            summary?: MultiEvalSummary;
          } | null;
        }>(`/model-train/multi-station-eval/status/${multiEvalTaskId}`);
        if (cancelled) return;
        if (r.status === "COMPLETED" && r.results) {
          setMultiEvalResult({
            results: r.results.results ?? [],
            summary: r.results.summary ?? {
              total_stations: 0,
              cc: { improved_count: 0, degraded_count: 0 },
              rmse: { improved_count: 0, degraded_count: 0 },
              mae: { improved_count: 0, degraded_count: 0 },
              mre: { improved_count: 0, degraded_count: 0 },
              mbe: { improved_count: 0, degraded_count: 0 },
              r2: { improved_count: 0, degraded_count: 0 },
            },
          });
        }
        if (r.status === "COMPLETED" || r.status === "FAILED")
          setMultiEvalTaskId("");
      } catch { /* 静默 */ }
    };
    void poll();
    const timer = setInterval(() => void poll(), 2000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [multiEvalTaskId]);

  function renderMultiEval(): ReactNode {
    const { summary } = multiEvalResult ?? {
      summary: null,
    };
    const evalResults = multiEvalResult?.results ?? [];

    return (
      <>
        {/* 配置 */}
        <div className="card">
          <div className="card-header">
            <h2>评估配置</h2>
            <button
              className="btn btn-primary"
              disabled={busy === "multi-eval" || !!multiEvalTaskId || !multiEvalForm.model_file}
              onClick={() => void startMultiEval()}
            >
              {busy === "multi-eval" ? "提交中..." : multiEvalTaskId ? "评估中..." : "开始评估"}
            </button>
          </div>

          <div className="field-grid cols-3">
            <div className="field">
              <label>模型类型</label>
              <select
                value={multiEvalForm.model_name}
                onChange={(e) =>
                  setMultiEvalForm((c) => ({
                    ...c,
                    model_name: e.target.value as "XGBoost" | "LightGBM",
                  }))
                }
              >
                <option value="XGBoost">XGBoost</option>
                <option value="LightGBM">LightGBM</option>
              </select>
            </div>
            <div className="field">
              <label>气象要素</label>
              <select
                value={multiEvalForm.element}
                onChange={(e) =>
                  setMultiEvalForm((c) => ({ ...c, element: e.target.value }))
                }
              >
                {ELEMENTS.map((el) => (
                  <option key={el} value={el}>{el}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>季节</label>
              <select
                value={multiEvalForm.season}
                onChange={(e) =>
                  setMultiEvalForm((c) => ({ ...c, season: e.target.value }))
                }
              >
                {SEASONS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="field-grid cols-3" style={{ marginTop: 12 }}>
            <div className="field">
              <label>模型文件名</label>
              <input
                value={multiEvalForm.model_file}
                onChange={(e) =>
                  setMultiEvalForm((c) => ({ ...c, model_file: e.target.value }))
                }
                placeholder="模型文件路径或文件名"
              />
            </div>
            <div className="field">
              <label>开始年份</label>
              <input
                value={multiEvalForm.start_year}
                onChange={(e) =>
                  setMultiEvalForm((c) => ({ ...c, start_year: e.target.value }))
                }
              />
            </div>
            <div className="field">
              <label>结束年份</label>
              <input
                value={multiEvalForm.end_year}
                onChange={(e) =>
                  setMultiEvalForm((c) => ({ ...c, end_year: e.target.value }))
                }
              />
            </div>
          </div>
        </div>

        {/* 汇总统计 */}
        {summary && (
          <div className="card">
            <div className="card-header">
              <h2>评估汇总</h2>
              <span style={{ color: "var(--text-dim)", fontSize: "0.85rem" }}>
                共 {summary.total_stations} 个站点
              </span>
            </div>
            <table className="metrics-table">
              <thead>
                <tr>
                  <th>指标</th>
                  <th>改善站点数</th>
                  <th>退化站点数</th>
                </tr>
              </thead>
              <tbody>
                {(["CC", "RMSE", "MAE", "MRE", "MBE", "R2"] as const).map(
                  (name) => {
                    const m = summary[name as keyof MultiEvalSummary];
                    const data = m as { improved_count: number; degraded_count: number };
                    return (
                      <tr key={name}>
                        <td style={{ fontWeight: 600 }}>{name}</td>
                        <td className="improved">{data.improved_count}</td>
                        <td className="degraded">{data.degraded_count}</td>
                      </tr>
                    );
                  }
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* 逐站点结果 */}
        {evalResults.length > 0 && (
          <div className="card">
            <div className="card-header">
              <h2>逐站点结果</h2>
              {multiEvalTaskId === "" && (
                <a
                  href={`${baseUrl.replace(/\/$/, "")}/model-train/multi-station-eval/export/${encodeURIComponent(multiEvalTaskId || "")}`}
                  className="btn btn-ghost btn-sm"
                  onClick={(e) => {
                    e.preventDefault();
                    void runAction("export-eval", async () => {
                      window.open(
                        `${baseUrl.replace(/\/$/, "")}/model-train/multi-station-eval/export/${encodeURIComponent(multiEvalTaskId || "")}`
                      );
                    });
                  }}
                >
                  导出 Excel
                </a>
              )}
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="metrics-table">
                <thead>
                  <tr>
                    <th>站点</th>
                    <th>纬度</th>
                    <th>经度</th>
                    <th>模型 CC</th>
                    <th>格点 CC</th>
                    <th>模型 RMSE</th>
                    <th>格点 RMSE</th>
                    <th>模型 MAE</th>
                    <th>格点 MAE</th>
                    <th>模型 R2</th>
                    <th>格点 R2</th>
                  </tr>
                </thead>
                <tbody>
                  {evalResults.map((r) => (
                    <tr key={r.station_id}>
                      <td style={{ fontWeight: 600 }}>{r.station_name}</td>
                      <td>{fmt(r.lat, 2)}</td>
                      <td>{fmt(r.lon, 2)}</td>
                      <td className={r.diff_cc_improved ? "improved" : "degraded"}>
                        {fmt(r.model_cc)}
                      </td>
                      <td>{fmt(r.grid_cc)}</td>
                      <td className={r.diff_rmse_improved ? "improved" : "degraded"}>
                        {fmt(r.model_rmse)}
                      </td>
                      <td>{fmt(r.grid_rmse)}</td>
                      <td className={r.diff_mae_improved ? "improved" : "degraded"}>
                        {fmt(r.model_mae)}
                      </td>
                      <td>{fmt(r.grid_mae)}</td>
                      <td className={r.diff_r2_improved ? "improved" : "degraded"}>
                        {fmt(r.model_r2)}
                      </td>
                      <td>{fmt(r.grid_r2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 空状态 */}
        {!multiEvalResult && !multiEvalTaskId && (
          <Empty>
            配置模型参数后点击"开始评估"，系统将批量评估所有站点的模型效果
          </Empty>
        )}
        {multiEvalTaskId && (
          <div className="card">
            <div className="task-top">
              <strong>评估任务执行中</strong>
              <StatusPill status="PROCESSING" />
            </div>
            <p style={{ color: "var(--text-dim)", fontSize: "0.82rem", marginTop: 8 }}>
              正在逐站点计算评估指标，请等待完成...
            </p>
          </div>
        )}
      </>
    );
  }

  /* ===== 任务监控 ===== */

  async function cancelTask() {
    if (!taskDetail.parent.task_id) return;
    await runAction("cancel", async () => {
      const r = await api<{ message: string }>(
        `/task_operate/${taskDetail.parent.task_id}/cancel`,
        { method: "POST" }
      );
      addLog("取消请求已发送", r.message, "info");
      await refreshTaskDetail(taskDetail.parent.task_id);
    });
  }

  function renderTasks(): ReactNode {
    const filterOptions: Array<{
      key: TaskFilter;
      label: string;
    }> = [
      { key: "ALL", label: "全部" },
      { key: "PROCESSING", label: "运行中" },
      { key: "COMPLETED", label: "已完成" },
      { key: "FAILED", label: "失败" },
      { key: "PENDING", label: "等待中" },
    ];

    return (
      <>
        {/* 筛选栏 */}
        <div className="card">
          <div className="card-header">
            <h2>任务历史</h2>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => void refreshTasks()}
            >
              刷新列表
            </button>
          </div>

          <div className="chip-row" style={{ marginBottom: 12 }}>
            {filterOptions.map((f) => (
              <button
                key={f.key}
                className={`chip${taskFilter === f.key ? " selected" : ""}`}
                onClick={() => setTaskFilter(f.key)}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="field-grid cols-2">
            <div className="field">
              <label>搜索任务</label>
              <input
                value={taskSearch}
                onChange={(e) => setTaskSearch(e.target.value)}
                placeholder="任务名 / 类型 / ID"
              />
            </div>
            <div className="field">
              <label>排序</label>
              <select
                value={
                  taskSearch > "" ? "name" : "progress_desc"
                }
                onChange={(e) => setTaskSearch(e.target.value)}
              >
                <option value="progress_desc">按进度从高到低</option>
                <option value="progress_asc">按进度从低到高</option>
                <option value="name">按名称排序</option>
              </select>
            </div>
          </div>
        </div>

        {/* 任务列表 */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {filteredTasks.length > 0 ? (
            filteredTasks.map((t) => (
              <button
                key={t.task_id}
                className={`task-item${selectedTaskId === t.task_id ? " selected" : ""}`}
                onClick={() => setSelectedTaskId(t.task_id)}
              >
                <div className="task-top">
                  <strong>{t.task_name}</strong>
                  <StatusPill status={t.status} />
                </div>
                <div className="task-meta">
                  <span>{t.task_type}</span>
                  <span>{t.progress}%</span>
                </div>
                <ProgressBar value={t.progress} slim />
              </button>
            ))
          ) : (
            <Empty>
              当前筛选条件下没有任务，切换状态或清空关键词后重试
            </Empty>
          )}
        </div>
      </>
    );
  }

  function renderModuleContent(): ReactNode {
    switch (moduleKey) {
      case "dashboard":
        return renderDashboard();
      case "settings":
        return renderSettings();
      case "import":
        return renderImport();
      case "process":
        return renderProcess();
      case "train":
        return renderTrain();
      case "correct":
        return renderCorrect();
      case "pivot":
        return renderPivot();
      case "multieval":
        return renderMultiEval();
      case "tasks":
        return renderTasks();
      default:
        return null;
    }
  }

  /* ----- 渲染 ----- */
  return (
    <div className="app-shell">
      {/* 顶栏 */}
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">WC</div>
          <div>
            <div className="brand-title">气象订正工作台</div>
            <div className="brand-sub">
              围绕任务流与数据透视统一管理处理、训练、订正与分析
            </div>
          </div>
        </div>
        <div className="topbar-right">
          <input
            className="topbar-input"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="后端地址"
          />
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => void refreshBase()}
          >
            重连
          </button>
          <div
            className={`service-tag ${online ? "online" : "offline"}`}
          >
            {online ? "在线" : "离线"}
          </div>
        </div>
      </header>

      {/* 主布局 */}
      <div className="main-layout">
        {/* 侧栏 */}
        <aside className="sidebar">
          <div className="sidebar-label">业务流程</div>
          {MODULES.map((m) => (
            <button
              key={m.key}
              className={`sidebar-item${moduleKey === m.key ? " active" : ""}`}
              onClick={() => setModuleKey(m.key)}
            >
              <strong>{m.title}</strong>
              <small>{m.desc}</small>
            </button>
          ))}
        </aside>

        {/* 内容区 */}
        <div className="content-area">
          <div className="content-header">
            <div>
              <h1>{currentModule?.title}</h1>
              <p>{currentModule?.desc}</p>
            </div>
            <div className="header-stats">
              <span className="stat-chip processing">
                执行中 {stats.processing}
              </span>
              <span className="stat-chip completed">
                已完成 {stats.completed}
              </span>
              <span className="stat-chip failed">
                失败 {stats.failed}
              </span>
            </div>
          </div>

          <div
            className={`content-body${moduleKey === "pivot" ? " fullscreen-pivot" : ""}`}
          >
            {/* 主内容 */}
            <section className="main-content">
              {renderModuleContent()}
            </section>

            {/* 侧面板 — 任务监控 + 日志 */}
            {moduleKey !== "pivot" && (
              <aside className="side-content">
                {/* 模块实时任务 */}
                <div className="side-section">
                  <div className="section-title">
                    模块任务 · {moduleTasks.length}
                  </div>
                  {moduleTasks.length > 0 ? (
                    moduleTasks.map((t) => (
                      <button
                        key={t.task_id}
                        className={`task-item${selectedTaskId === t.task_id ? " selected" : ""}`}
                        onClick={() => setSelectedTaskId(t.task_id)}
                      >
                        <div className="task-top">
                          <strong>{t.task_name}</strong>
                          <StatusPill status={t.status} />
                        </div>
                        <div className="task-meta">
                          <span>{t.task_type}</span>
                          <span>{t.progress}%</span>
                        </div>
                        <ProgressBar value={t.progress} slim />
                      </button>
                    ))
                  ) : (
                    <Empty>当前模块暂无任务</Empty>
                  )}
                </div>

                {/* 当前任务详情 */}
                <div className="side-section">
                  <div className="section-title">任务详情</div>
                  {taskDetail.parent.task_id ? (
                    <>
                      <div className="highlight-row">
                        <div className="highlight-item">
                          <span>总子任务</span>
                          <strong>{taskSummary.total}</strong>
                        </div>
                        <div className="highlight-item">
                          <span>进行中</span>
                          <strong>{taskSummary.processing}</strong>
                        </div>
                        <div className="highlight-item">
                          <span>已完成</span>
                          <strong>{taskSummary.completed}</strong>
                        </div>
                        <div className="highlight-item">
                          <span>失败</span>
                          <strong>{taskSummary.failed}</strong>
                        </div>
                      </div>
                      <div className="card">
                        <div className="task-top">
                          <strong>{taskDetail.parent.task_name}</strong>
                          <StatusPill status={taskDetail.parent.status} />
                        </div>
                        <div className="task-meta">
                          <span>{taskDetail.parent.task_type}</span>
                          <span>{taskDetail.parent.progress}%</span>
                        </div>
                        <ProgressBar value={taskDetail.parent.progress} />
                        <p style={{ color: "var(--text-dim)", fontSize: "0.82rem", marginTop: 8 }}>
                          {taskDetail.parent.progress_text || "等待进度回传"}
                        </p>
                      </div>
                      {(taskDetail.parent.status === "PROCESSING" ||
                        taskDetail.parent.status === "PENDING") && (
                        <button
                          className="btn btn-danger btn-sm"
                          disabled={busy === "cancel"}
                          onClick={async () => {
                            await runAction("cancel", async () => {
                              const r = await api<{ message: string }>(
                                `/task_operate/${taskDetail.parent.task_id}/cancel`,
                                { method: "POST" }
                              );
                              addLog("取消任务", r.message, "info");
                              await refreshTaskDetail(
                                taskDetail.parent.task_id
                              );
                            });
                          }}
                        >
                          {busy === "cancel" ? "取消中..." : "取消任务"}
                        </button>
                      )}
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {taskDetail.sub_tasks.slice(0, 10).map((st) => (
                          <div className="subtask-item" key={st.task_id}>
                            <div className="subtask-top">
                              <strong>{st.task_name}</strong>
                              <StatusPill status={st.status} />
                            </div>
                            <ProgressBar value={st.progress} slim />
                            <small>{st.progress_text || `${st.progress}%`}</small>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : (
                    <Empty>选择任务查看详情</Empty>
                  )}
                </div>

                {/* 操作日志 */}
                <div className="side-section">
                  <div className="section-title">
                    操作日志 · {logs.length}
                  </div>
                  <div className="log-list">
                    {logs.length > 0 ? (
                      logs.map((l) => (
                        <div
                          className={`log-item ${l.tone}`}
                          key={l.id}
                        >
                          <strong>{l.title}</strong>
                          <p>{l.detail}</p>
                        </div>
                      ))
                    ) : (
                      <Empty>操作结果将显示在此</Empty>
                    )}
                  </div>
                </div>
              </aside>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
