"use client";
/** The drawing's title block, bottom-right, as on any drafted sheet. Facts only. */
import { Fragment } from "react";
import { useSheet } from "@/lib/store";
import { useSummary } from "@/lib/queries";
import { format } from "date-fns";

export default function TitleBlock({ sheet, lens }: { sheet?: string; lens: string }) {
  return null;
}
