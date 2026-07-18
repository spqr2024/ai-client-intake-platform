/**
 * The shared primitives carry the app's accessibility contract — if these
 * regress, every screen regresses at once.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmptyState, ErrorState, LoadingState, Pagination, Toast } from "./ui";

describe("LoadingState", () => {
  it("announces loading to assistive tech", () => {
    render(<LoadingState label="Loading leads" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading leads");
  });
});

describe("EmptyState", () => {
  it("explains the situation and offers the next action", () => {
    render(
      <EmptyState
        title="No leads yet"
        description="Leads appear here after a chat."
        action={<button>Open widget</button>}
      />
    );
    expect(screen.getByRole("heading", { name: "No leads yet" })).toBeInTheDocument();
    expect(screen.getByText("Leads appear here after a chat.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open widget" })).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("uses an alert role so screen readers interrupt", () => {
    render(<ErrorState message="Server unreachable" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Server unreachable");
  });

  it("retries through the supplied callback", async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Boom" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("omits the retry affordance when recovery is not possible", () => {
    render(<ErrorState message="Boom" />);
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });
});

describe("Toast", () => {
  it("uses alert for errors and status for confirmations", () => {
    const { unmount } = render(<Toast kind="err" message="Save failed" />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    unmount();

    render(<Toast kind="ok" message="Saved" />);
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
  });

  it("dismisses via a labelled control", async () => {
    const onDismiss = vi.fn();
    render(<Toast kind="ok" message="Saved" onDismiss={onDismiss} />);
    await userEvent.click(screen.getByRole("button", { name: "Dismiss message" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});

describe("Pagination", () => {
  it("stays hidden when everything fits on one page", () => {
    const { container } = render(
      <Pagination total={10} limit={25} offset={0} onChange={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("reports the visible range and total", () => {
    render(<Pagination total={120} limit={25} offset={25} onChange={vi.fn()} />);
    expect(screen.getByLabelText("Pagination")).toBeInTheDocument();
    expect(screen.getByText(/Page 2 of 5/)).toBeInTheDocument();
    expect(screen.getByText("26")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
  });

  it("disables Prev on the first page and Next on the last", () => {
    const { unmount } = render(
      <Pagination total={120} limit={25} offset={0} onChange={vi.fn()} />
    );
    expect(screen.getByRole("button", { name: /Prev/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Next/ })).toBeEnabled();
    unmount();

    render(<Pagination total={120} limit={25} offset={100} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Next/ })).toBeDisabled();
  });

  it("moves by exactly one page", async () => {
    const onChange = vi.fn();
    render(<Pagination total={120} limit={25} offset={25} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /Next/ }));
    expect(onChange).toHaveBeenCalledWith(50);
    await userEvent.click(screen.getByRole("button", { name: /Prev/ }));
    expect(onChange).toHaveBeenCalledWith(0);
  });

  it("never produces a negative offset", async () => {
    const onChange = vi.fn();
    render(<Pagination total={120} limit={25} offset={10} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /Prev/ }));
    expect(onChange).toHaveBeenCalledWith(0);
  });
});
