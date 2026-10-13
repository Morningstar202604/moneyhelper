/** useStreamingMutate：apiStream SSE 流式问答的统一收口（useMutate 的流式变体）。
 *
 *  设计：把「发起一次流式问答 + 流式过程逐帧回调 + settle 收尾」收口到 useMutation。
 *  - mutate(body) 的 body 形如 { payload, onEvent }：onEvent 是逐帧回调（做增量 patch 消息）；
 *  - mutationFn 内部创建 AbortController，调 run(payload, onEvent, signal)；
 *  - res 携带 aborted 标志（AbortError 视为用户主动取消，不算失败）；
 *  - onSettled 每次 settle 都触发：store.bump() + 回调（aborted 便于调用方区分「取消」与「真失败」）。
 *
 *  与 useMutate 一致：不吞错（Abort 之外的失败正常抛），调用方按需弹 toast / 回写消息。
 */

import { useCallback, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { store } from "@/lib/store";

type StreamEvent = (ev: Record<string, unknown>) => void;

export interface StreamBody<TPayload> {
  payload: TPayload;
  onEvent: StreamEvent;
}

interface UseStreamingMutateOptions<TPayload> {
  /** 发起流式请求：payload 为业务 body；onEvent 逐帧回调 */
  run: (payload: TPayload, onEvent: StreamEvent, signal: AbortSignal) => Promise<void>;
  /** settle 收尾（成功/失败/取消都触发）：aborted 标记是否用户主动取消 */
  onSettled?: (payload: TPayload, aborted: boolean, err: unknown) => void;
}

export function useStreamingMutate<TPayload>(
  opts: UseStreamingMutateOptions<TPayload>,
) {
  const abortRef = useRef<AbortController | null>(null);

  /** 外部调用点多传 StreamBody：{ payload, onEvent }；hook 内部拆开走 */
  const m = useMutation({
    mutationFn: async (body: StreamBody<TPayload>): Promise<{ aborted: boolean }> => {
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await opts.run(body.payload, body.onEvent, controller.signal);
        return { aborted: false };
      } catch (err) {
        const aborted = (err as Error)?.name === "AbortError" || controller.signal.aborted;
        if (aborted) return { aborted: true };
        throw err; // 真实失败（网络/500/解析错误）向上抛，让 onError/onSettled 的 err 生效
      } finally {
        abortRef.current = null;
      }
    },
    onSettled: (_res, err, body) => {
      // 取回 res.aborted：仅用户主动取消时为 true；真实失败时 _res 为 undefined 且 err 非空
      const resAborted = ((_res as { aborted?: boolean } | undefined)?.aborted ?? false);
      store.bump();
      opts.onSettled?.(body.payload, resAborted, err);
    },
  });

  const stop = useCallback(() => abortRef.current?.abort(), []);

  return {
    isPending: m.isPending,
    mutate: m.mutate,
    stop,
  };
}
