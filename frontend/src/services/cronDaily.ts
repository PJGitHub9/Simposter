/** Whether a 5-field cron runs at least once every day (day of month, month
 *  and weekday all "*"). Used to suggest a daily Overlay Refresh when overlays
 *  use Maintainerr's {leaving} values, which change from day to day. */
export const cronRunsDaily = (cron: string | null | undefined): boolean => {
  const parts = String(cron || '').trim().split(/\s+/)
  return parts.length === 5 && parts[2] === '*' && parts[3] === '*' && parts[4] === '*'
}
