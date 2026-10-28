// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  act,
} from "@testing-library/react";
import { PresetSelector } from "./PresetSelector";
const presets = [
  {
    id: "chaen",
    title: "Chaen",
    description: "Matcha",
    location: "New York",
    prompt: "A full prompt for Chaen.\nWith the exact second line.",
  },
  {
    id: "humo",
    title: "Humo Santo",
    description: "Mezcal",
    location: "Austin",
    prompt: "A full prompt for Humo Santo.",
  },
  {
    id: "nocturne-botanica-london",
    title: "Nocturne Botanica",
    description: "Perfume oil",
    location: "London, UK",
    prompt:
      "Launch a London, UK campaign for 'Nocturne Botanica', a smoky hinoki and fig skin-scent perfume oil for gallery directors, pilates regulars, and late-night wine bar readers. Channel the world of Aesop, Byredo, and FKA twigs, stealing buyers from Jo Malone.",
  },
  {
    id: "vespera",
    title: "Vespera",
    description: "Aperitif",
    location: "Chicago, IL",
    prompt: "Run a Chicago campaign for Vespera.",
  },
  {
    id: "salina",
    title: "Salina Club",
    description: "Electrolyte aperitif",
    location: "Miami, FL",
    prompt: "Launch Salina Club in Miami.",
  },
];
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
function setup() {
  const select = vi.fn();
  render(<PresetSelector presets={presets} busy={false} onSelect={select} />);
  return { select };
}
it("previews the exact prompt for each preset without starting Ask", () => {
  const { select } = setup();
  for (const preset of presets) {
    const button = screen.getByRole("button", { name: preset.title });
    fireEvent.pointerEnter(button);
    const preview = screen.getByRole("tooltip");
    expect(preview.querySelector("p")?.textContent).toBe(preset.prompt);
    expect(button.getAttribute("aria-describedby")).toBe(preview.id);
  }
  expect(select).not.toHaveBeenCalled();
});
it("bridges the pointer gap and remains readable until the pointer leaves", () => {
  vi.useFakeTimers();
  setup();
  const button = screen.getByRole("button", { name: "Chaen" });
  fireEvent.pointerEnter(button);
  const preview = screen.getByRole("tooltip");
  fireEvent.pointerLeave(button);
  act(() => {
    vi.advanceTimersByTime(100);
  });
  expect(screen.getByRole("tooltip")).toBeTruthy();
  fireEvent.pointerEnter(preview);
  act(() => {
    vi.advanceTimersByTime(400);
  });
  expect(screen.getByRole("tooltip")).toBeTruthy();
  fireEvent.pointerLeave(preview);
  act(() => {
    vi.advanceTimersByTime(151);
  });
  expect(screen.queryByRole("tooltip")).toBeNull();
  expect(preview.querySelector("p")?.textContent).toBe(presets[0].prompt);
});
it("supports focus, Escape, and unchanged click-to-start behavior", () => {
  vi.useFakeTimers();
  const { select } = setup();
  const button = screen.getByRole("button", { name: "Chaen" });
  fireEvent.focus(button);
  expect(screen.getByRole("tooltip")).toBeTruthy();
  fireEvent.keyDown(button, { key: "Escape" });
  expect(screen.queryByRole("tooltip")).toBeNull();
  expect(button.hasAttribute("aria-describedby")).toBe(false);
  fireEvent.blur(button);
  fireEvent.focus(screen.getByRole("button", { name: "Humo Santo" }));
  expect(screen.getByRole("tooltip").querySelector("p")?.textContent).toBe(
    presets[1].prompt,
  );
  fireEvent.click(screen.getByRole("button", { name: "Humo Santo" }));
  expect(select).toHaveBeenCalledWith(presets[1].prompt);
  fireEvent.pointerEnter(button);
  fireEvent.pointerEnter(screen.getByRole("button", { name: "Next presets" }));
  expect(screen.queryByRole("tooltip")).toBeNull();
  expect(screen.queryByRole("button", { name: /Try the Ask flow/ })).toBeNull();
});
it("scrolls to reveal more presets and enables returning to the first page", () => {
  setup();
  const track = screen
    .getByRole("group", { name: "Campaign presets" })
    .querySelector(".preset-list") as HTMLDivElement;
  Object.defineProperties(track, {
    clientWidth: { value: 600 },
    scrollWidth: { value: 1000 },
  });
  track.scrollBy = vi.fn();
  fireEvent.click(screen.getByRole("button", { name: "Next presets" }));
  expect(track.scrollBy).toHaveBeenCalledWith({
    left: 600,
    behavior: "smooth",
  });
  track.scrollLeft = 400;
  fireEvent.scroll(track);
  expect(
    (screen.getByRole("button", { name: "Next presets" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Previous presets" }));
  expect(track.scrollBy).toHaveBeenLastCalledWith({
    left: -600,
    behavior: "smooth",
  });
});
it("starts the newly revealed preset with its exact prompt", () => {
  const { select } = setup();
  fireEvent.focus(screen.getByRole("button", { name: "Salina Club" }));
  expect(screen.getByRole("tooltip").querySelector("p")?.textContent).toBe(
    presets[4].prompt,
  );
  fireEvent.click(screen.getByRole("button", { name: "Salina Club" }));
  expect(select).toHaveBeenCalledWith(presets[4].prompt);
});
