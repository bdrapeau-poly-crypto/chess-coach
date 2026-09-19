import {
  Chart as ChartJS,
  Filler,
  Legend,
  LineElement,
  PointElement,
  RadialLinearScale,
  Tooltip,
} from "chart.js";
import { Radar } from "react-chartjs-2";
import type { StyleGap } from "../types";

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip, Legend);

const FIELDS = ["aggression", "tactical", "positional", "endgame", "risk"];

export function StyleRadar({ gap }: { gap: StyleGap }) {
  return (
    <Radar
      data={{
        labels: FIELDS.map((field) => field[0].toUpperCase() + field.slice(1)),
        datasets: [
          {
            label: gap.username,
            data: FIELDS.map((field) => gap.player[field]),
            backgroundColor: "rgba(200, 90, 63, .2)",
            borderColor: "#c85a3f",
          },
          {
            label: gap.gm_name,
            data: FIELDS.map((field) => gap.grandmaster[field]),
            backgroundColor: "rgba(31, 75, 55, .14)",
            borderColor: "#1f4b37",
          },
        ],
      }}
      options={{
        responsive: true,
        scales: { r: { min: 0, max: 100, ticks: { display: false } } },
      }}
    />
  );
}
