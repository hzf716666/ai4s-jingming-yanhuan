import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UserMessage } from "./atoms";

// copyText hits the OS clipboard — stub it so the copy button is observable.
const { copyTextMock } = vi.hoisted(() => ({ copyTextMock: vi.fn(async () => {}) }));
vi.mock("@/lib/clipboard", () => ({ copyText: copyTextMock }));
vi.mock("@/lib/toast", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const dialog = () => screen.getByRole("alertdialog");

describe("UserMessage", () => {
  afterEach(() => vi.clearAllMocks());

  it("renders the text in a right-aligned, content-hugging bubble", () => {
    const { container } = render(<UserMessage block={{ kind: "user", text: "部署" }} />);
    expect(screen.getByText("部署")).toBeInTheDocument();
    // Right-aligned column, bubble hugs its content (short prompts stay small).
    expect(container.querySelector(".items-end")).not.toBeNull();
    expect(container.querySelector(".w-fit")).not.toBeNull();
  });

  it("shows Edit/Revert only when the message has an id AND the handler", () => {
    const { rerender } = render(<UserMessage block={{ kind: "user", text: "hi", messageID: "m1" }} />);
    expect(screen.queryByLabelText("编辑")).toBeNull(); // no handlers
    expect(screen.queryByLabelText("回退")).toBeNull();
    rerender(<UserMessage block={{ kind: "user", text: "hi" }} onEdit={() => {}} onRevert={() => {}} />);
    expect(screen.queryByLabelText("编辑")).toBeNull(); // no id
    expect(screen.queryByLabelText("回退")).toBeNull();
    rerender(
      <UserMessage block={{ kind: "user", text: "hi", messageID: "m1" }} onEdit={() => {}} onRevert={() => {}} />,
    );
    expect(screen.getByLabelText("编辑")).toBeInTheDocument();
    expect(screen.getByLabelText("回退")).toBeInTheDocument();
  });

  it("edit resends only after the destructive-action dialog is confirmed", () => {
    const onEdit = vi.fn();
    render(<UserMessage block={{ kind: "user", text: "部署", messageID: "m1" }} onEdit={onEdit} />);
    fireEvent.click(screen.getByLabelText("编辑"));
    const area = screen.getByRole("textbox") as HTMLTextAreaElement;
    expect(area.value).toBe("部署");
    fireEvent.change(area, { target: { value: "部署到生产" } });
    fireEvent.click(screen.getByText("发送"));
    // The dialog gates the destructive resend — nothing sent yet.
    expect(onEdit).not.toHaveBeenCalled();
    fireEvent.click(within(dialog()).getByText("修改并重发"));
    expect(onEdit).toHaveBeenCalledWith("m1", "部署到生产");
    expect(screen.queryByRole("textbox")).toBeNull(); // editor closed
  });

  it("cancelling the dialog keeps the editor open and sends nothing", () => {
    const onEdit = vi.fn();
    render(<UserMessage block={{ kind: "user", text: "部署", messageID: "m1" }} onEdit={onEdit} />);
    fireEvent.click(screen.getByLabelText("编辑"));
    fireEvent.click(screen.getByText("发送"));
    fireEvent.click(within(dialog()).getByText("取消"));
    expect(onEdit).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox")).toBeInTheDocument(); // still editing
  });

  it("refuses to open the dialog for an empty edit", () => {
    render(<UserMessage block={{ kind: "user", text: "hi", messageID: "m1" }} onEdit={() => {}} />);
    fireEvent.click(screen.getByLabelText("编辑"));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "   " } });
    const send = screen.getByText("发送") as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.click(send);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("revert rolls back to the message and prefills only after confirmation", () => {
    const onRevert = vi.fn();
    render(<UserMessage block={{ kind: "user", text: "部署", messageID: "m1" }} onRevert={onRevert} />);
    fireEvent.click(screen.getByLabelText("回退"));
    expect(onRevert).not.toHaveBeenCalled(); // dialog gates it
    fireEvent.click(within(dialog()).getByText("回退到这里"));
    expect(onRevert).toHaveBeenCalledWith("m1", "部署");
  });

  it("cancelling the revert dialog does nothing", () => {
    const onRevert = vi.fn();
    render(<UserMessage block={{ kind: "user", text: "部署", messageID: "m1" }} onRevert={onRevert} />);
    fireEvent.click(screen.getByLabelText("回退"));
    fireEvent.click(within(dialog()).getByText("取消"));
    expect(onRevert).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("copies the message text to the clipboard", () => {
    render(<UserMessage block={{ kind: "user", text: "部署" }} />);
    fireEvent.click(screen.getByLabelText("复制"));
    expect(copyTextMock).toHaveBeenCalledWith("部署");
  });
});
