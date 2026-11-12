import type { MetadataRoute } from "next";
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "AEP-X Hybrid IDE",
    short_name: "AEP-X",
    description: "Governed agentic development workspace",
    id: "/",
    start_url: "/",
    display: "standalone",
    background_color: "#0b1020",
    theme_color: "#101a2d",
    icons: [{src:"/icon.svg",sizes:"any",type:"image/svg+xml",purpose:"any"}]
  };
}
