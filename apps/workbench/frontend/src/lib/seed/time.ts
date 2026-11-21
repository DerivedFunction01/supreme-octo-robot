// Relative stamp builders for the seed, derived from
// the seed's `now` (the mock adapter's clock reading
// at build time).

export interface SeedTime {
  minsAgo(m: number): string;
  hoursAgo(h: number): string;
}

export function seedTime(now: Date): SeedTime {
  const minsAgo = (m: number) =>
    new Date(now.getTime() - m * 60_000).toISOString();
  const hoursAgo = (h: number) => minsAgo(h * 60);
  return { minsAgo, hoursAgo };
}
