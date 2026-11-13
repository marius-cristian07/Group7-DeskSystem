// The height-over-time chart (S4-4), drawn as SVG without a chart library.
// Horizontal axis: the time each reading was saved. Vertical axis: height in millimetres.
//
// Rules the drawing follows (the maths is in utils/chartGeometry.js):
//  - Every dot is one saved reading, placed at its saved timestamp.
//  - The line stops where readings are missing. It never crosses a gap, and the gap is
//    shaded, so a period with no readings cannot be mistaken for measured data.
//  - The axis covers the whole selected range, so an empty stretch stays visibly empty.

import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { buildChart } from '../utils/chartGeometry';
import { formatClock, formatDateTime, formatDuration } from '../utils/historyRules';

const CHART_HEIGHT = 240;
// Used until the real width is measured (and where the browser cannot measure).
const FALLBACK_WIDTH = 320;
// Above this many readings only the line is drawn; dots would overlap into a smear.
const MAX_DOTS = 150;

// The width available to the chart, kept current when the dialog or window is resized.
// The dialog is closed while the first measurement runs; the observer reports the
// real width as soon as it opens.
function useElementWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    const measure = () => setWidth(Math.floor(element.getBoundingClientRect().width));
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

export default function HeightChart({ prepared }) {
  const [wrapperRef, measuredWidth] = useElementWidth();
  const width = measuredWidth > 0 ? measuredWidth : FALLBACK_WIDTH;
  const chart = useMemo(() => buildChart({ prepared, width, height: CHART_HEIGHT }), [prepared, width]);

  const patternId = useId();
  const titleId = useId();
  const descId = useId();

  const { points } = prepared;
  const latest = points[points.length - 1];
  const lowest = Math.min(...points.map((point) => point.height));
  const highest = Math.max(...points.map((point) => point.height));
  const description =
    `${points.length} saved reading${points.length === 1 ? '' : 's'} from ${formatDateTime(points[0].t)} ` +
    `to ${formatDateTime(latest.t)}. Lowest ${lowest} millimetres, highest ${highest} millimetres, ` +
    `latest ${latest.height} millimetres.`;

  const { plot } = chart;
  const plotRight = plot.left + plot.width;
  const plotBottom = plot.top + plot.height;
  const showAllDots = points.length <= MAX_DOTS;

  return (
    <figure className="history-chart" ref={wrapperRef}>
      <svg width={width} height={CHART_HEIGHT} role="img" aria-labelledby={`${titleId} ${descId}`}>
        <title id={titleId}>Desk height over time</title>
        <desc id={descId}>{description}</desc>

        <defs>
          <pattern id={patternId} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="7" className="history-chart__hatch" />
          </pattern>
        </defs>

        {/* Periods with no saved readings, drawn first so the lines sit on top. */}
        {chart.gaps.map((gap) => (
          <rect
            key={`${gap.from}-${gap.to}`}
            x={gap.x}
            y={plot.top}
            width={gap.width}
            height={plot.height}
            fill={`url(#${patternId})`}
          >
            <title>{`No readings saved from ${formatClock(gap.from)} to ${formatClock(gap.to)}`}</title>
          </rect>
        ))}

        {chart.yTicks.map((tick) => (
          <g key={tick.value}>
            <line x1={plot.left} x2={plotRight} y1={tick.y} y2={tick.y} className="history-chart__grid" />
            <text x={plot.left - 8} y={tick.y} dy="0.32em" textAnchor="end">{tick.value}</text>
          </g>
        ))}

        <line x1={plot.left} x2={plot.left} y1={plot.top} y2={plotBottom} className="history-chart__axis" />
        <line x1={plot.left} x2={plotRight} y1={plotBottom} y2={plotBottom} className="history-chart__axis" />

        {chart.xTicks.map((tick) => (
          <g key={tick.t}>
            <line x1={tick.x} x2={tick.x} y1={plotBottom} y2={plotBottom + 4} className="history-chart__axis" />
            {/* A label at the far right would be cut off if it were centred on its tick. */}
            <text x={tick.x} y={plotBottom + 18} textAnchor={tick.x > plotRight - 20 ? 'end' : 'middle'}>
              {tick.label}
            </text>
          </g>
        ))}

        <text className="history-chart__axis-title" transform={`translate(14 ${plot.top + plot.height / 2}) rotate(-90)`} textAnchor="middle">
          Height (mm)
        </text>
        <text className="history-chart__axis-title" x={plot.left + plot.width / 2} y={CHART_HEIGHT - 6} textAnchor="middle">
          Recording time (your local time)
        </text>

        {chart.segments.map((segment) => (
          <g key={segment.dots[0].t}>
            {segment.path && <path d={segment.path} className="history-chart__line" />}
            {/* A reading with no neighbour has no line, so it is always drawn as a dot. */}
            {(showAllDots || segment.dots.length === 1) &&
              segment.dots.map((dot) => (
                <circle
                  key={dot.id ?? dot.t}
                  cx={dot.x}
                  cy={dot.y}
                  r={segment.dots.length === 1 ? 4 : 2.5}
                  className="history-chart__dot"
                >
                  <title>{`${dot.height} mm at ${formatClock(dot.t, true)}`}</title>
                </circle>
              ))}
          </g>
        ))}
      </svg>

      <figcaption className="history-chart__caption">
        <span>Latest saved reading: <strong>{latest.height} mm</strong> at {formatClock(latest.t, true)}</span>
        <span>Lowest {lowest} mm · Highest {highest} mm · {points.length} reading{points.length === 1 ? '' : 's'}</span>
      </figcaption>

      <ul className="history-chart__legend">
        <li><span className="swatch swatch--reading" aria-hidden="true" /> A saved reading</li>
        {chart.gaps.length > 0 && (
          <li><span className="swatch swatch--gap" aria-hidden="true" /> No readings saved</li>
        )}
      </ul>
      <p className="desk-dialog__note">
        The line is broken wherever more than {formatDuration(prepared.gapThresholdMs)} passed without a saved
        reading. Nothing is drawn for those periods, because the desk was not measured then.
      </p>
    </figure>
  );
}
