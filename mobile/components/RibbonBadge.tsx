/**
 * RibbonBadge — award-ribbon rosette with scalloped outer ring,
 * gold centre circle, rank text, and two hanging tails.
 *
 * rank: 1 | 2 | 3
 */
import React from 'react';
import Svg, {
  Circle, Ellipse, Path, Text as SvgText, G,
} from 'react-native-svg';

// Design tokens
const DS = {
  navy900: '#0E2A47',
  navy700: '#1B4B79',
  okSolid:    '#2E7D32',
  dangerSolid:'#C62828',
  starFill:   '#F2A900',
  starText:   '#B07A00',
};

const CONFIGS = {
  1: { body: DS.navy900,    bodyDark: DS.navy700,    label: '1st', a11y: 'First place'  },
  2: { body: DS.dangerSolid, bodyDark: '#8B1A1A',    label: '2nd', a11y: 'Second place' },
  3: { body: DS.okSolid,    bodyDark: '#1B5226',     label: '3rd', a11y: 'Third place'  },
} as const;

const GOLD   = DS.starFill;
const GOLD_D = DS.starText;
const W = 54;
const H = 82;
const CX = W / 2;          // 32
const CY = 33;              // rosette centre y
const OUTER_R  = 28;        // scallop orbit radius
const SCALLOP_R = 8;        // radius of each scallop circle
const INNER_R  = 19;        // dark centre
const RING_R   = 21;        // gold ring
const PETALS   = 18;        // number of scallop circles

interface Props { rank: 1 | 2 | 3; size?: number; }

export default function RibbonBadge({ rank, size = 1 }: Props) {
  const cfg = CONFIGS[rank];

  // Build the scalloped outer ring as overlapping circles
  const scallops: JSX.Element[] = [];
  for (let i = 0; i < PETALS; i++) {
    const angle = (i / PETALS) * 2 * Math.PI - Math.PI / 2;
    const sx = CX + OUTER_R * Math.cos(angle);
    const sy = CY + OUTER_R * Math.sin(angle);
    scallops.push(
      <Circle key={i} cx={sx} cy={sy} r={SCALLOP_R}
              fill={i % 2 === 0 ? cfg.body : cfg.bodyDark} />
    );
  }

  const scale = size;

  return (
    <Svg
      width={W * scale}
      height={H * scale}
      viewBox={`0 0 ${W} ${H}`}
      accessibilityLabel={cfg.a11y}
      accessibilityRole="image"
    >
      {/* ── Ribbon tails ──────────────────────────────────────────────── */}
      {/* Left tail */}
      <Path
        d={`M ${CX - 10} ${CY + INNER_R + 4} L ${CX - 14} ${H} L ${CX} ${H - 8} Z`}
        fill={cfg.bodyDark}
      />
      {/* Right tail */}
      <Path
        d={`M ${CX + 10} ${CY + INNER_R + 4} L ${CX + 14} ${H} L ${CX} ${H - 8} Z`}
        fill={cfg.body}
      />
      {/* Tail stripe lines */}
      <Path
        d={`M ${CX - 2} ${CY + INNER_R + 6} L ${CX - 8} ${H - 4}`}
        stroke={cfg.bodyDark} strokeWidth={2} opacity={0.5}
      />
      <Path
        d={`M ${CX + 2} ${CY + INNER_R + 6} L ${CX + 8} ${H - 4}`}
        stroke={cfg.body} strokeWidth={2} opacity={0.5}
      />

      {/* ── Scalloped rosette ring ─────────────────────────────────────── */}
      <G>{scallops}</G>

      {/* Solid disc behind centre so petals don't show through */}
      <Circle cx={CX} cy={CY} r={RING_R + 2} fill={cfg.body} />

      {/* ── Gold ring ─────────────────────────────────────────────────── */}
      <Circle cx={CX} cy={CY} r={RING_R}
              fill="none" stroke={GOLD} strokeWidth={2.5} />

      {/* ── Dark centre circle ────────────────────────────────────────── */}
      <Circle cx={CX} cy={CY} r={INNER_R} fill={cfg.bodyDark} />

      {/* ── Gold inner ring ───────────────────────────────────────────── */}
      <Circle cx={CX} cy={CY} r={INNER_R - 1}
              fill="none" stroke={GOLD_D} strokeWidth={1} opacity={0.6} />

      {/* ── Rank text ─────────────────────────────────────────────────── */}
      <SvgText
        x={CX} y={CY}
        textAnchor="middle"
        dominantBaseline="central"
        fill={GOLD}
        fontSize={13}
        fontWeight="bold"
        fontFamily="-apple-system, sans-serif"
      >
        {cfg.label}
      </SvgText>
    </Svg>
  );
}
