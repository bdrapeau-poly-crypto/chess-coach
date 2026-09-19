import { Bar } from "react-chartjs-2";
import {
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Tooltip,
} from "chart.js";
import type { Weakness } from "../types";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

export function WeaknessChart({ weaknesses }: { weaknesses: Weakness[] }) {
  return (
    <Bar
      data={{
        labels: weaknesses.map((item) => item.theme.replaceAll("_", " ")),
        datasets: [
          {
            label: "Occurrences",
            data: weaknesses.map((item) => item.frequency),
            backgroundColor: "#c85a3f",
            borderRadius: 6,
          },
        ],
      }}
      options={{ responsive: true, plugins: { legend: { display: false } } }}
    />
  );
}
