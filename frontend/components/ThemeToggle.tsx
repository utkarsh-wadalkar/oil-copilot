"use client";

import { Moon, Sun } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

type Theme = "light" | "dark";

const STORAGE_KEY = "fieldnote-theme";

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark") return stored;
  return "dark";
}

/**
 * Light/dark toggle. Defaults to dark; the choice is persisted in localStorage
 * and applied to <html data-theme="..."> before first paint via the inline
 * script in layout.tsx.
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    setTheme(getInitialTheme());
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const isDark = theme === "dark";

  return (
    <button
      type="button"
      className="button button--quiet"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      title={isDark ? "Switch to light theme" : "Switch to dark theme"}
    >
      {isDark ? <Sun size={16} weight="regular" aria-hidden="true" /> : <Moon size={16} weight="regular" aria-hidden="true" />}
      <span className="sr-only">{isDark ? "Switch to light theme" : "Switch to dark theme"}</span>
    </button>
  );
}
