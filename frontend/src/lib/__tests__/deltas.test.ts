import { changeOf, pointsOf } from "@/lib/deltas";

test("relative change says which way and whether it is good", () => {
  expect(changeOf(112, 100, 30)).toEqual({ text: "↑ 12% vs previous 30 days", good: true });
  expect(changeOf(80, 100, 7)).toEqual({ text: "↓ 20% vs previous 7 days", good: false });
  expect(changeOf(80, 100, 30, "down")).toEqual({ text: "↓ 20% vs previous 30 days", good: true });
  expect(changeOf(120, 100, 30, "none")?.good).toBeNull();
});

test("no previous period means no claim, and zero to zero is no change", () => {
  expect(changeOf(5, null, 30)).toBeNull();
  expect(changeOf(0, 0, 30)).toEqual({ text: "No change vs previous 30 days", good: null });
  expect(changeOf(9, 0, 30)).toEqual({ text: "New this period", good: true });
});

test("rates change in points, not percent of a percent", () => {
  expect(pointsOf(0.88, 0.85, 30)).toEqual({ text: "↑ 3 pts vs previous 30 days", good: true });
  expect(pointsOf(0.5, 0.5, 30)?.good).toBeNull();
  expect(pointsOf(null, 0.5, 30)).toBeNull();
});
