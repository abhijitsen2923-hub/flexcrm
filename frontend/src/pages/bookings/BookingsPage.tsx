import { useEffect, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { ClipboardCheck, Plus } from "lucide-react";
import { Badge, Button, Card, DataTable, EmptyState } from "../../components";
import type { DataTableColumn } from "../../components";
import { useBookings } from "../../hooks/useBookings";
import { inventoryService } from "../../services/inventory";
import { LoadingBlock } from "../../components/ui/Spinner";
import { BookingWizard } from "./components/BookingWizard";
import type { Booking, Unit } from "../../types/realestate";
import { formatDate } from "../../utils/format";
import "./BookingsPage.css";

const STATUS_TONE = {
  draft: "warning",
  confirmed: "success",
  cancelled: "neutral",
} as const;

const COLUMNS: DataTableColumn<Booking>[] = [
  {
    key: "id",
    header: "Booking",
    render: (b) => <span className="mono">{b.id.slice(0, 8)}…</span>,
  },
  {
    key: "unit",
    header: "Unit",
    render: (b) =>
      b.unit ? `${b.unit.projectName} · ${b.unit.towerName} · ${b.unit.unitNumber}` : "—",
  },
  { key: "step", header: "Step", render: (b) => `${b.step} / 4` },
  {
    key: "status",
    header: "Status",
    render: (b) => (
      <Badge tone={STATUS_TONE[b.status] ?? "neutral"}>
        {b.status.charAt(0).toUpperCase() + b.status.slice(1)}
      </Badge>
    ),
  },
  {
    key: "scheduledDate",
    header: "Registration Date",
    render: (b) => (b.scheduledDate ? formatDate(b.scheduledDate) : "—"),
  },
  {
    key: "createdAt",
    header: "Created",
    render: (b) => formatDate(b.createdAt),
  },
];

export default function BookingsPage() {
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const navState = location.state as { projectName?: string; towerName?: string } | null;
  const preselectedUnitId = searchParams.get("unitId");
  const { bookings, loading, refresh, create } = useBookings();
  const [wizardUnit, setWizardUnit] = useState<
    (Pick<Unit, "id" | "unitNumber" | "floor" | "area" | "basePrice"> & { towerName: string; projectName: string }) | null
  >(null);

  // If navigated from inventory with ?unitId=, pre-open wizard
  useEffect(() => {
    if (!preselectedUnitId) return;
    inventoryService.getUnit(preselectedUnitId).then((unit) => {
      setWizardUnit({
        ...unit,
        towerName: navState?.towerName ?? "Tower",
        projectName: navState?.projectName ?? "Project",
      });
    }).catch(() => {});
  }, [preselectedUnitId, navState?.towerName, navState?.projectName]);

  if (loading) return <LoadingBlock label="Loading bookings…" />;

  return (
    <div className="bookings-page">
      <div className="page-header">
        <h1 className="page-title">Bookings</h1>
        <Button variant="primary" icon={<Plus size={16} />}>
          New Booking
        </Button>
      </div>

      {bookings.length === 0 ? (
        <EmptyState
          icon={<ClipboardCheck size={32} />}
          title="No bookings yet"
          description="Start a booking from the Inventory board or use the button above."
        />
      ) : (
        <Card>
          <DataTable
            columns={COLUMNS}
            rows={bookings}
            rowKey={(b) => b.id}
          />
        </Card>
      )}

      {wizardUnit && (
        <BookingWizard
          unit={wizardUnit}
          onClose={() => setWizardUnit(null)}
          onComplete={(booking) => {
            refresh();
            setWizardUnit(null);
          }}
        />
      )}
    </div>
  );
}
