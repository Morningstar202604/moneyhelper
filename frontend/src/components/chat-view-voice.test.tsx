/**
 * 语音输入 hook 的行为测试。
 *
 * 覆盖的是真实分支：浏览器不支持时提示、支持时构造识别器并把文本写回输入框、
 * 以及识别语言跟随界面语言（此前硬编码 zh-CN）。
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";
import { Toaster } from "@/lib/toast";
import { useVoiceInput } from "./chat-view-hooks";

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <I18nProvider>
      <Toaster />
      {children}
    </I18nProvider>
  );
}

/** 一个可控的假 SpeechRecognition 实现 */
class FakeRecognition {
  static instances: FakeRecognition[] = [];
  lang = "";
  interimResults = true;
  onresult: ((e: unknown) => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  started = false;
  stopped = false;

  constructor() {
    FakeRecognition.instances.push(this);
  }
  start() {
    this.started = true;
  }
  stop() {
    this.stopped = true;
    this.onend?.();
  }
  emit(text: string) {
    this.onresult?.({ results: [[{ transcript: text }]] });
  }
}

afterEach(() => {
  FakeRecognition.instances = [];
  delete (window as unknown as Record<string, unknown>).SpeechRecognition;
  delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
});

describe("useVoiceInput", () => {
  it("浏览器不支持时给出提示且不抛错", () => {
    const setInput = vi.fn();
    const { result } = renderHook(() => useVoiceInput(setInput), { wrapper });
    expect(() => act(() => result.current.toggleVoice())).not.toThrow();
    expect(result.current.listening).toBe(false);
    expect(setInput).not.toHaveBeenCalled();
  });

  it("支持时启动识别器，识别结果写回输入框", () => {
    (window as unknown as Record<string, unknown>).SpeechRecognition = FakeRecognition;
    const setInput = vi.fn();
    const { result } = renderHook(() => useVoiceInput(setInput), { wrapper });

    act(() => result.current.toggleVoice());
    expect(result.current.listening).toBe(true);
    expect(FakeRecognition.instances).toHaveLength(1);

    act(() => FakeRecognition.instances[0].emit("这个月花了多少"));
    // setInput 用函数式更新：取出更新函数并用空串调用，验证追加内容
    const updater = setInput.mock.calls[0][0] as (v: string) => string;
    expect(updater("")).toBe("这个月花了多少");
  });

  it("再次点击会停止识别并复位 listening", () => {
    (window as unknown as Record<string, unknown>).SpeechRecognition = FakeRecognition;
    const { result } = renderHook(() => useVoiceInput(vi.fn()), { wrapper });

    act(() => result.current.toggleVoice());
    act(() => result.current.toggleVoice());
    expect(result.current.listening).toBe(false);
    expect(FakeRecognition.instances[0].stopped).toBe(true);
  });

  it("识别语言跟随界面语言（中文界面 zh-CN / 英文界面 en-US）", () => {
    (window as unknown as Record<string, unknown>).SpeechRecognition = FakeRecognition;

    localStorage.setItem("wo.lang", "zh");
    const zh = renderHook(() => useVoiceInput(vi.fn()), { wrapper });
    act(() => zh.result.current.toggleVoice());
    expect(FakeRecognition.instances[0].lang).toBe("zh-CN");
    zh.unmount();

    localStorage.setItem("wo.lang", "en");
    const en = renderHook(() => useVoiceInput(vi.fn()), { wrapper });
    act(() => en.result.current.toggleVoice());
    expect(FakeRecognition.instances[1].lang).toBe("en-US");
  });

  it("webkit 前缀同样可用（Safari/旧版 Chrome）", () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;
    const { result } = renderHook(() => useVoiceInput(vi.fn()), { wrapper });
    act(() => result.current.toggleVoice());
    expect(FakeRecognition.instances).toHaveLength(1);
  });
});
