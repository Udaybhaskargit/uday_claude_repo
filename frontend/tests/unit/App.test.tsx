import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "../../src/App";

describe("App shell", () => {
  it("renders the role-select page at the root route", () => {
    render(
      <BrowserRouter>
        <App />
      </BrowserRouter>,
    );

    expect(
      screen.getByRole("heading", { name: /claimflow/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/actor id/i)).toBeInTheDocument();
  });
});
