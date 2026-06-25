// Per-trader visual identity. Keyed by first name (lowercased) so it lines up
// with the backend roster (Warren, George, Ray, Cathie).

export interface TraderTheme {
  accent: string;
  accentSoft: string;
  glow: string;
  emoji: string;
  tagline: string;
}

const THEMES: Record<string, TraderTheme> = {
  warren: {
    accent: "#38bdf8",
    accentSoft: "rgba(56, 189, 248, 0.14)",
    glow: "rgba(56, 189, 248, 0.45)",
    emoji: "🧭",
    tagline: "Patient value investor",
  },
  george: {
    accent: "#fb7185",
    accentSoft: "rgba(251, 113, 133, 0.14)",
    glow: "rgba(251, 113, 133, 0.45)",
    emoji: "🔥",
    tagline: "Bold macro risk-taker",
  },
  ray: {
    accent: "#34d399",
    accentSoft: "rgba(52, 211, 153, 0.14)",
    glow: "rgba(52, 211, 153, 0.45)",
    emoji: "📐",
    tagline: "Systematic quant",
  },
  cathie: {
    accent: "#c084fc",
    accentSoft: "rgba(192, 132, 252, 0.14)",
    glow: "rgba(192, 132, 252, 0.45)",
    emoji: "🚀",
    tagline: "Disruptive growth seeker",
  },
};

const FALLBACK: TraderTheme = {
  accent: "#94a3b8",
  accentSoft: "rgba(148, 163, 184, 0.14)",
  glow: "rgba(148, 163, 184, 0.4)",
  emoji: "🤖",
  tagline: "Autonomous AI trader",
};

export function traderTheme(name: string): TraderTheme {
  return THEMES[name.toLowerCase()] ?? FALLBACK;
}

export function initials(name: string, lastname: string): string {
  return `${name[0] ?? ""}${lastname[0] ?? ""}`.toUpperCase();
}
