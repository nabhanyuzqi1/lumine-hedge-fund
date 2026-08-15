import { describe, expect, it, vi } from "vitest";
import { SHORTCUTS, isModActive, isTypingTarget, matchShortcut, resolveShortcut } from "./keyboard";

describe("keyboard", () => {
  describe("isModActive", () => {
    it("returns metaKey on macOS", () => {
      vi.stubGlobal("navigator", { platform: "MacIntel" });
      expect(isModActive(new KeyboardEvent("keydown", { metaKey: true }))).toBe(true);
      expect(isModActive(new KeyboardEvent("keydown", { ctrlKey: true }))).toBe(false);
      vi.unstubAllGlobals();
    });

    it("returns ctrlKey on Windows/Linux", () => {
      vi.stubGlobal("navigator", { platform: "Win32" });
      expect(isModActive(new KeyboardEvent("keydown", { ctrlKey: true }))).toBe(true);
      expect(isModActive(new KeyboardEvent("keydown", { metaKey: true }))).toBe(false);
      vi.unstubAllGlobals();
    });
  });

  describe("isTypingTarget", () => {
    it("returns true for input", () => {
      const input = document.createElement("input");
      const event = new KeyboardEvent("keydown", { key: "k", bubbles: true });
      input.dispatchEvent(event);
      expect(isTypingTarget(event)).toBe(true);
    });

    it("returns false for div", () => {
      const div = document.createElement("div");
      const event = new KeyboardEvent("keydown", { key: "k", bubbles: true });
      div.dispatchEvent(event);
      expect(isTypingTarget(event)).toBe(false);
    });
  });

  describe("matchShortcut", () => {
    it("matches mod+k", () => {
      vi.stubGlobal("navigator", { platform: "MacIntel" });
      const event = new KeyboardEvent("keydown", { key: "k", metaKey: true });
      expect(matchShortcut(event, SHORTCUTS["command-palette:toggle"])).toBe(true);
      vi.unstubAllGlobals();
    });

    it("does not match without mod", () => {
      const event = new KeyboardEvent("keydown", { key: "k" });
      expect(matchShortcut(event, SHORTCUTS["command-palette:toggle"])).toBe(false);
    });
  });

  describe("resolveShortcut", () => {
    it("resolves command palette toggle", () => {
      vi.stubGlobal("navigator", { platform: "MacIntel" });
      const event = new KeyboardEvent("keydown", { key: "k", metaKey: true });
      expect(resolveShortcut(event)).toBe("command-palette:toggle");
      vi.unstubAllGlobals();
    });

    it("resolves workspace shortcuts", () => {
      vi.stubGlobal("navigator", { platform: "MacIntel" });
      expect(resolveShortcut(new KeyboardEvent("keydown", { key: "1", metaKey: true }))).toBe(
        "workspace:trading"
      );
      expect(resolveShortcut(new KeyboardEvent("keydown", { key: "2", metaKey: true }))).toBe(
        "workspace:research"
      );
      expect(resolveShortcut(new KeyboardEvent("keydown", { key: "3", metaKey: true }))).toBe(
        "workspace:risk"
      );
      expect(resolveShortcut(new KeyboardEvent("keydown", { key: "4", metaKey: true }))).toBe(
        "workspace:ops"
      );
      vi.unstubAllGlobals();
    });

    it("still resolves command palette toggle when focus is in input", () => {
      vi.stubGlobal("navigator", { platform: "MacIntel" });
      const input = document.createElement("input");
      const event = new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true });
      input.dispatchEvent(event);
      expect(resolveShortcut(event)).toBe("command-palette:toggle");
      vi.unstubAllGlobals();
    });

    it("returns null for unmatched keys", () => {
      vi.stubGlobal("navigator", { platform: "MacIntel" });
      const event = new KeyboardEvent("keydown", { key: "z", metaKey: true });
      expect(resolveShortcut(event)).toBeNull();
      vi.unstubAllGlobals();
    });
  });
});
