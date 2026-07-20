/**
 * Access control for the admin shell.
 *
 * The rule under test is "no admin content reaches the DOM unless the server
 * confirmed the session". A token in localStorage is a claim, not proof, so
 * every case here asserts on the absence of `children` — not merely that a
 * redirect was requested, since a redirect that races the render still leaks
 * the page.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
const push = vi.fn();
let pathname = "/admin";

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ replace, push }),
}));

/** Stands in for GET /api/auth/me only. */
const api = vi.fn();
const getToken = vi.fn();
const setTokens = vi.fn();

vi.mock("@/lib/api", () => ({
  // The shell also polls /api/notifications from the bell. Route that to an
  // empty list so these tests exercise the guard rather than the bell.
  api: (path: string, ...rest: unknown[]) =>
    path.startsWith("/api/notifications") ? Promise.resolve([]) : api(path, ...rest),
  getToken: () => getToken(),
  setTokens: (...args: unknown[]) => setTokens(...args),
  logout: vi.fn(),
}));

import AdminLayout from "./layout";

const SECRET = "Confidential lead pipeline";

function renderAdmin() {
  return render(
    <AdminLayout>
      <p>{SECRET}</p>
    </AdminLayout>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  pathname = "/admin";
});

describe("admin route guard", () => {
  it("renders no admin content and redirects when there is no token", async () => {
    getToken.mockReturnValue(null);

    renderAdmin();

    expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/login"));
    // The identity endpoint must not even be called without a token.
    expect(api).not.toHaveBeenCalled();
  });

  it("never renders children while the session is still being verified", () => {
    getToken.mockReturnValue("a-token");
    // A promise that never settles models a slow /api/auth/me.
    api.mockReturnValue(new Promise(() => {}));

    renderAdmin();

    expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
    expect(screen.getByText(/verifying your session/i)).toBeInTheDocument();
  });

  it("discards the credentials when the token is rejected", async () => {
    getToken.mockReturnValue("expired-or-forged");
    api.mockRejectedValue(new Error("401 Unauthorized"));

    renderAdmin();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/login"));
    // Regression guard: this failure used to be swallowed, leaving a bad token
    // parked on a fully rendered admin shell.
    expect(setTokens).toHaveBeenCalledWith(null, null);
    expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
  });

  it("renders the app once the server confirms an admin", async () => {
    getToken.mockReturnValue("good-token");
    api.mockResolvedValue({ id: 1, name: "Root", email: "a@b.c", role: "admin", workspace_id: 1 });

    renderAdmin();

    expect(await screen.findByText(SECRET)).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("refuses an admin-only route to a non-admin who navigates directly", async () => {
    pathname = "/admin/settings";
    getToken.mockReturnValue("good-token");
    api.mockResolvedValue({ id: 2, name: "Mgr", email: "m@b.c", role: "manager", workspace_id: 1 });

    renderAdmin();

    expect(await screen.findByText(/administrator access only/i)).toBeInTheDocument();
    expect(screen.queryByText(SECRET)).not.toBeInTheDocument();
    // Hiding the sidebar link is presentation; the route itself must refuse.
    expect(screen.queryByRole("link", { name: /settings/i })).not.toBeInTheDocument();
  });

  it("still allows a non-admin into the shared sections", async () => {
    pathname = "/admin";
    getToken.mockReturnValue("good-token");
    api.mockResolvedValue({ id: 2, name: "Mgr", email: "m@b.c", role: "manager", workspace_id: 1 });

    renderAdmin();

    expect(await screen.findByText(SECRET)).toBeInTheDocument();
  });

  it("does not guard the login page itself", () => {
    pathname = "/admin/login";
    getToken.mockReturnValue(null);

    renderAdmin();

    // The login page must render for logged-out users, or nobody can sign in.
    expect(screen.getByText(SECRET)).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
