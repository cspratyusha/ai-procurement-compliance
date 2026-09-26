/**
 * The StandEng wordmark. Served from /logo.svg (a copy of the project's
 * logo.svg with its viewBox cropped to the artwork; the original sits on a
 * mostly empty 1500x1500 canvas and would render tiny).
 *
 * Height drives size; width follows the artwork's ~2.9:1 ratio.
 */
export default function Logo({ height = 28, className = '' }) {
  return (
    <img
      src="/logo.svg"
      alt="StandEng"
      height={height}
      width={Math.round(height * 2.92)}
      className={`logo-img ${className}`}
      draggable="false"
    />
  );
}
