/**
 * The API client owns the silent token-refresh flow — the piece most likely to
 * log every user out if it regresses, and the hardest to notice by hand.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  api,
  ApiError,
  formatBudget,
  getRefreshToken,
  getToken,
  logout,
  priorityColor,
  scoreColor,
  setTokens,
  statusColor,
} from "./api";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("token storage", () => {
  it("stores and clears both tokens", () => {
    setTokens("access-1", "refresh-1");
    expect(getToken()).toBe("access-1");
    expect(getRefreshToken()).toBe("refresh-1");

    setTokens(null, null);
    expect(getToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it("leaves the refresh token untouched when omitted", () => {
    setTokens("access-1", "refresh-1");
    setTokens("access-2");
    expect(getToken()).toBe("access-2");
    expect(getRefreshToken()).toBe("refresh-1");
  });
});

describe("api()", () => {
  beforeEach(() => setTokens(null, null));

  it("attaches the bearer token only when auth is requested", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    setTokens("access-1", "refresh-1");

    await api("/api/public/branding");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined();

    await api("/api/auth/me", {}, true);
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer access-1");
  });

  it("returns undefined for 204 responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(api("/api/notifications/read-all", { method: "POST" }, true)).resolves.toBeUndefined();
  });

  it("throws ApiError carrying the server detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "Lead not found" }, 404))
    );
    await expect(api("/api/leads/999", {}, true)).rejects.toMatchObject({
      status: 404,
      message: "Lead not found",
    });
    await expect(api("/api/leads/999", {}, true)).rejects.toBeInstanceOf(ApiError);
  });

  it("refreshes once on 401 and replays the original request", async () => {
    setTokens("expired", "refresh-1");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "Invalid or expired token" }, 401))
      .mockResolvedValueOnce(jsonResponse({ access_token: "fresh", refresh_token: "refresh-2" }))
      .mockResolvedValueOnce(jsonResponse({ id: 1, name: "Admin" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api("/api/auth/me", {}, true)).resolves.toMatchObject({ name: "Admin" });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toContain("/api/auth/refresh");
    // The replay must carry the NEW access token, not the expired one.
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe("Bearer fresh");
    expect(getToken()).toBe("fresh");
    expect(getRefreshToken()).toBe("refresh-2");
  });

  it("does not retry forever when the refresh itself fails", async () => {
    setTokens("expired", "refresh-1");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401))
      .mockResolvedValueOnce(jsonResponse({ detail: "invalid refresh" }, 401));
    vi.stubGlobal("fetch", fetchMock);
    // jsdom has no navigation; swallow the redirect the client performs.
    Object.defineProperty(window, "location", { value: { href: "" }, writable: true });

    await expect(api("/api/auth/me", {}, true)).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(getToken()).toBeNull();
  });
});

describe("logout", () => {
  it("revokes the refresh token server-side and clears storage", async () => {
    setTokens("access-1", "refresh-1");
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await logout();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain("/api/auth/logout");
    expect(getToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it("still clears local tokens when the server call fails", async () => {
    setTokens("access-1", "refresh-1");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    await logout();
    expect(getToken()).toBeNull();
  });
});

describe("display helpers", () => {
  it("formats budgets and handles the unknown case", () => {
    expect(formatBudget(5000)).toBe("$5,000");
    expect(formatBudget(null)).toBe("—");
  });

  it("maps every pipeline status and priority to a style", () => {
    for (const status of ["New", "Qualified", "In Progress", "Converted", "Rejected"]) {
      expect(statusColor(status)).toMatch(/bg-/);
    }
    // Custom workspace stages must still render, not crash.
    expect(statusColor("Proposal Sent")).toMatch(/bg-/);
    for (const priority of ["Low", "Medium", "High", "Urgent"]) {
      expect(priorityColor(priority)).toMatch(/text-/);
    }
  });

  it("colours scores by band", () => {
    expect(scoreColor(85)).toContain("emerald");
    expect(scoreColor(50)).toContain("amber");
    expect(scoreColor(10)).toContain("rose");
  });
});
