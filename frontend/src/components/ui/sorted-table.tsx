import { useState, useDeferredValue, useMemo, useEffect, type ReactNode } from "react";
import {
  createColumnHelper,
  createCoreRowModel,
  createSortedRowModel,
  createFilteredRowModel,
  rowSortingFeature,
  columnFilteringFeature,
  globalFilteringFeature,
  filterFns,
  coreFeatures,
  tableFeatures,
  constructTable,
  type Table,
  type RowData,
} from "@tanstack/table-core";
import {
  table_getRowModel,
  table_setSorting,
  table_setGlobalFilter,
} from "@tanstack/table-core/static-functions";
import { ChevronUp, ChevronDown, Search, ArrowUpDown, FileX } from "lucide-react";
import { cn } from "@/lib/utils";

/** 列定义接口 */
export interface ColumnDef<T> {
  key: string;
  header: string;
  sortable?: boolean;
  align?: "left" | "center" | "right";
  className?: string;
  /** 自定义渲染函数；未设置时显示 accessor 原始值 */
  render?: (row: T) => ReactNode;
  /** 列宽度（CSS 值，如 "120px"、"15%"） */
  width?: string;
}

interface Props<T> {
  columns: ColumnDef<T>[];
  rows: T[];
  /** 可搜索的字段 key；为空数组时不显示搜索框 */
  searchKeys?: string[];
  searchPlaceholder?: string;
  emptyText?: string;
  /** 初始排序字段 */
  initialSortKey?: string;
  /** 行 key 生成函数；未设置时使用 index */
  rowKey?: (row: T, index: number) => string;
  onRowClick?: (row: T) => void;
  getRowClassName?: (row: T) => string;
  className?: string;
  /** 表头吸顶 */
  stickyHeader?: boolean;
  /** 容器最大高度（需要 overflow-auto 时传，如 "60vh"、"500px"） */
  maxHeight?: string;
}

/** 排序方向图标 */
function SortIcon({ sortKey, sortDir, colKey }: { sortKey: string | null; sortDir: "asc" | "desc"; colKey: string }) {
  if (sortKey === colKey) {
    return sortDir === "asc" ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />;
  }
  return <ArrowUpDown className="h-3 w-3 opacity-40" />;
}

// ---------------------------------------------------------------------------
// TanStack Table v9：特性集（静态注册，复用）
//  - coreFeatures: 基础表/列/行/表头/单元格能力
//  - rowSortingFeature: 排序状态与列 API
//  - columnFilteringFeature + globalFilteringFeature: 全局搜索
//  - coreRowModel / sortedRowModel / filteredRowModel: 行模型流水线
// ---------------------------------------------------------------------------
const features = tableFeatures({
  ...coreFeatures,
  rowSortingFeature,
  columnFilteringFeature,
  globalFilteringFeature,
  coreRowModel: createCoreRowModel(),
  sortedRowModel: createSortedRowModel(),
  filteredRowModel: createFilteredRowModel(),
});

// 列辅助工具（宽泛类型；调用时断言为 unknown 以匹配 any 数据行）
const columnHelper = createColumnHelper();

// 表实例类型别名（用 any 绕过复杂的泛型推导）
type AnyTable = Table<any, RowData>;

export function SortedTable<T extends object>({
  columns,
  rows,
  searchKeys = [],
  searchPlaceholder = "Search...",
  emptyText = "暂无数据",
  initialSortKey,
  rowKey,
  onRowClick,
  getRowClassName,
  className,
  stickyHeader = false,
  maxHeight,
}: Props<T>) {
  const [searchInput, setSearchInput] = useState("");
  const [sortKey, setSortKey] = useState<string | null>(initialSortKey ?? null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  // useDeferredValue 让搜索输入不阻塞 UI 响应
  const search = useDeferredValue(searchInput);

  // 将自定义 ColumnDef 转换为 TanStack 列定义
  const tanstackColumns = useMemo(() => {
    return columns.map((col) =>
      columnHelper.display({
        id: col.key,
        header: col.header,
        enableSorting: false,
        enableGlobalFilter: searchKeys.includes(col.key),
        meta: {
          customKey: col.key,
          align: col.align,
          className: col.className,
          width: col.width,
          customSortable: col.sortable !== false,
          customRender: col.render,
        },
        cell: (ctx: any) => {
          const rowData: Record<string, unknown> = ctx.row.original;
          if (col.render) return col.render(rowData as T);
          return String(rowData[col.key] ?? "");
        },
      })
    );
  }, [columns, searchKeys]);

  // 构建 TanStack Table 实例（在 data 或 columns 结构变化时重建）
  const table: AnyTable = useMemo(() => {
    return constructTable({
      features,
      data: rows as unknown as RowData[],
      columns: tanstackColumns,
      enableSorting: true,
      enableGlobalFilter: true,
      globalFilterFn: filterFns.includesString,
      initialState: {
        sorting: initialSortKey ? [{ id: initialSortKey, desc: false }] : [],
      },
      state: {
        globalFilter: "",
      },
    } as any);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, tanstackColumns, initialSortKey]);

  // 同步排序状态到 TanStack（副作用必须用 useEffect，不能用 useMemo）
  useEffect(() => {
    const sorting = sortKey ? [{ id: sortKey, desc: sortDir === "desc" }] : [];
    table_setSorting(table, sorting as any);
  }, [table, sortKey, sortDir]);

  // 同步搜索状态到 TanStack（副作用必须用 useEffect，不能用 useMemo）
  useEffect(() => {
    table_setGlobalFilter(table, search);
  }, [table, search]);

  // 从 TanStack 行模型流水线获取排序 + 过滤后的行
  const filteredRows = useMemo(() => {
    const model = table_getRowModel(table);
    return model.rows.map((r: any) => r.original as T);
  }, [table]);

  // 排序切换：asc → desc → asc 循环（与原实现保持一致）
  const toggleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const showSearch = searchKeys.length > 0;

  return (
    <div className={cn("space-y-2", className)}>
      {/* 搜索框 */}
      {showSearch && (
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder={searchPlaceholder}
            className="w-full rounded-md border border-input bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>
      )}

      {/* 表格容器 */}
      <div
        className={cn("overflow-x-auto rounded-lg border border-border", maxHeight && "overflow-y-auto")}
        style={maxHeight ? { maxHeight } : undefined}
      >
        <table className="w-full text-sm">
          <thead
            className={cn(
              "bg-muted/50 text-xs font-medium text-muted-foreground",
              stickyHeader && "sticky top-0 z-10 bg-background"
            )}
          >
            <tr>
              {columns.map((col) => {
                const canSort = col.sortable !== false;
                return (
                  <th
                    key={col.key}
                    style={col.width ? { width: col.width } : undefined}
                    onClick={() => canSort && toggleSort(col.key)}
                    className={cn(
                      "whitespace-nowrap px-4 py-2.5 font-medium select-none",
                      canSort && "cursor-pointer hover:text-foreground transition-colors",
                      col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : "text-left",
                      col.className
                    )}
                  >
                    <span className={cn("inline-flex items-center gap-1", col.align === "right" && "flex-row-reverse")}>
                      {col.header}
                      {canSort && (
                        <span className="text-[10px]">
                          <SortIcon sortKey={sortKey} sortDir={sortDir} colKey={col.key} />
                        </span>
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {filteredRows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-10 text-center text-muted-foreground">
                  <div className="flex flex-col items-center gap-2">
                    <FileX className="h-8 w-8 opacity-40" />
                    <span>{emptyText}</span>
                  </div>
                </td>
              </tr>
            ) : (
              filteredRows.map((row: T, idx: number) => (
                <tr
                  key={rowKey ? rowKey(row, idx) : String(idx)}
                  onClick={() => onRowClick?.(row)}
                  className={cn(
                    "border-t border-border transition-colors hover:bg-muted/50",
                    onRowClick && "cursor-pointer",
                    getRowClassName?.(row)
                  )}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn(
                        "px-4 py-2.5",
                        col.align === "right" ? "text-right tabular-nums" : col.align === "center" ? "text-center" : "text-left",
                        col.className
                      )}
                    >
                      {col.render
                        ? col.render(row)
                        : String((row as Record<string, unknown>)[col.key] ?? "")}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 底部信息栏 */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>共 {filteredRows.length} 条</span>
        {sortKey && (
          <span>
            按 {columns.find((c) => c.key === sortKey)?.header} {sortDir === "asc" ? "升序" : "降序"}
          </span>
        )}
      </div>
    </div>
  );
}
