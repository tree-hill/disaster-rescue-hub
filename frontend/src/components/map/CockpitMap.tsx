import { useEffect, useMemo, useRef, useState } from 'react';
import { Circle, Group, Layer, Line, Rect, Stage, Text } from 'react-konva';

import type { AlertRead } from '@/api/alerts';
import type { Position } from '@/api/robots';
import type { TaskRead } from '@/api/tasks';

export interface CockpitMapRobot {
  id: string;
  code: string;
  type: 'aerial' | 'ground' | 'marine';
  fsm: string;
  battery: number;
  position: Position | null;
  currentTaskId?: string | null;
}

type MapMode = 'pan' | 'select' | 'measure';

interface CockpitMapProps {
  robots: CockpitMapRobot[];
  tasks: TaskRead[];
  alerts: AlertRead[];
  mode: MapMode;
  zoom: number;
  resetKey: number;
  onZoomChange: (zoom: number) => void;
  onSelectionChange?: (label: string | null) => void;
}

interface ProjectedPoint {
  x: number;
  y: number;
}

const STAGE_WIDTH = 900;
const STAGE_HEIGHT = 640;
const MAP_PADDING = 72;
const MIN_ZOOM = 0.65;
const MAX_ZOOM = 2.4;

const DEFAULT_BOUNDS = {
  minLat: 30.18,
  maxLat: 30.32,
  minLng: 120.44,
  maxLng: 120.66,
};

const ROBOT_COLORS: Record<CockpitMapRobot['type'], string> = {
  aerial: '#60A5FA',
  ground: '#A78BFA',
  marine: '#22D3EE',
};

const TASK_COLORS: Record<number, string> = {
  1: '#EF4444',
  2: '#F59E0B',
  3: '#10B981',
};

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v));
}

function isPosition(v: unknown): v is Position {
  return (
    typeof v === 'object' &&
    v !== null &&
    typeof (v as Position).lat === 'number' &&
    typeof (v as Position).lng === 'number'
  );
}

function haversineMeters(a: Position, b: Position) {
  const earthRadiusM = 6371000;
  const p1 = (a.lat * Math.PI) / 180;
  const p2 = (b.lat * Math.PI) / 180;
  const dp = ((b.lat - a.lat) * Math.PI) / 180;
  const dl = ((b.lng - a.lng) * Math.PI) / 180;
  const s =
    Math.sin(dp / 2) ** 2 +
    Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * earthRadiusM * Math.asin(Math.sqrt(s));
}

function metersToLng(meters: number, lat: number) {
  return meters / (111320 * Math.max(0.1, Math.cos((lat * Math.PI) / 180)));
}

function yoloDetectionPosition(alert: AlertRead): Position | null {
  const detection = alert.payload.yolo_detection;
  if (!detection || typeof detection !== 'object') return null;
  const pos = (detection as { position?: unknown }).position;
  return isPosition(pos) ? pos : null;
}

function yoloDetectionClass(alert: AlertRead): string | null {
  const detection = alert.payload.yolo_detection;
  if (!detection || typeof detection !== 'object') return null;
  const className = (detection as { class_name?: unknown }).class_name;
  return typeof className === 'string' ? className : null;
}

function useContainerSize() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: STAGE_WIDTH, height: STAGE_HEIGHT });

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const update = () => {
      const rect = el.getBoundingClientRect();
      setSize({
        width: Math.max(320, rect.width),
        height: Math.max(260, rect.height),
      });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return { ref, size };
}

function collectBounds(robots: CockpitMapRobot[], tasks: TaskRead[], alerts: AlertRead[]) {
  const points: Position[] = [];
  robots.forEach((r) => {
    if (isPosition(r.position)) points.push(r.position);
  });
  tasks.forEach((t) => {
    if (isPosition(t.target_area.center_point)) points.push(t.target_area.center_point);
    if (t.target_area.bounds) {
      points.push(t.target_area.bounds.sw, t.target_area.bounds.ne);
    }
    t.target_area.vertices?.forEach((p) => points.push(p));
  });
  alerts.forEach((a) => {
    const pos = yoloDetectionPosition(a);
    if (isPosition(pos)) points.push(pos);
  });

  if (points.length === 0) return DEFAULT_BOUNDS;

  const lats = points.map((p) => p.lat);
  const lngs = points.map((p) => p.lng);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);
  const latPad = Math.max((maxLat - minLat) * 0.22, 0.01);
  const lngPad = Math.max((maxLng - minLng) * 0.22, 0.01);

  return {
    minLat: minLat - latPad,
    maxLat: maxLat + latPad,
    minLng: minLng - lngPad,
    maxLng: maxLng + lngPad,
  };
}

function createProjector(bounds: ReturnType<typeof collectBounds>, width: number, height: number) {
  const latSpan = Math.max(bounds.maxLat - bounds.minLat, 0.0001);
  const lngSpan = Math.max(bounds.maxLng - bounds.minLng, 0.0001);
  const innerW = Math.max(width - MAP_PADDING * 2, 1);
  const innerH = Math.max(height - MAP_PADDING * 2, 1);

  return {
    toXY(pos: Position): ProjectedPoint {
      return {
        x: MAP_PADDING + ((pos.lng - bounds.minLng) / lngSpan) * innerW,
        y: MAP_PADDING + ((bounds.maxLat - pos.lat) / latSpan) * innerH,
      };
    },
    toPosition(point: ProjectedPoint): Position {
      return {
        lat: bounds.maxLat - ((point.y - MAP_PADDING) / innerH) * latSpan,
        lng: bounds.minLng + ((point.x - MAP_PADDING) / innerW) * lngSpan,
      };
    },
  };
}

function formatDistance(meters: number) {
  return meters >= 1000 ? `${(meters / 1000).toFixed(2)} km` : `${Math.round(meters)} m`;
}

function taskRadiusPixels(task: TaskRead, project: ReturnType<typeof createProjector>) {
  const area = task.target_area;
  const center = area.center_point;
  if (area.type === 'circle' && area.radius_m) {
    const edge = {
      lat: center.lat,
      lng: center.lng + metersToLng(area.radius_m, center.lat),
    };
    return Math.max(14, Math.abs(project.toXY(edge).x - project.toXY(center).x));
  }
  return Math.max(18, Math.sqrt(Math.max(area.area_km2, 0.05)) * 26);
}

function taskPolygon(task: TaskRead, project: ReturnType<typeof createProjector>): number[] {
  const area = task.target_area;
  if (area.type === 'polygon' && area.vertices?.length) {
    return area.vertices.flatMap((p) => {
      const xy = project.toXY(p);
      return [xy.x, xy.y];
    });
  }
  if (area.type === 'rectangle' && area.bounds) {
    const { sw, ne } = area.bounds;
    const nw = { lat: ne.lat, lng: sw.lng };
    const se = { lat: sw.lat, lng: ne.lng };
    return [nw, ne, se, sw].flatMap((p) => {
      const xy = project.toXY(p);
      return [xy.x, xy.y];
    });
  }
  return [];
}

function RobotMarker({
  robot,
  point,
  onSelect,
}: {
  robot: CockpitMapRobot;
  point: ProjectedPoint;
  onSelect: () => void;
}) {
  const color = robot.fsm === 'FAULT' ? '#EF4444' : ROBOT_COLORS[robot.type];
  const size = robot.type === 'ground' ? 13 : 15;

  return (
    <Group x={point.x} y={point.y} onClick={onSelect} onTap={onSelect}>
      {robot.fsm === 'FAULT' && (
        <Circle radius={24} stroke="#EF4444" strokeWidth={1.4} dash={[4, 5]} opacity={0.86} />
      )}
      <Circle radius={size + 4} fill="#111827" stroke={color} strokeWidth={2} shadowColor={color} shadowBlur={10} shadowOpacity={0.28} />
      {robot.type === 'ground' ? (
        <Rect x={-7} y={-7} width={14} height={14} cornerRadius={3} fill={color} />
      ) : robot.type === 'marine' ? (
        <Line points={[0, -9, 9, 7, -9, 7]} closed fill={color} />
      ) : (
        <Line points={[0, -10, 9, 8, 0, 4, -9, 8]} closed fill={color} />
      )}
      <Text
        text={robot.code}
        x={-42}
        y={22}
        width={84}
        align="center"
        fontFamily="JetBrains Mono, monospace"
        fontSize={10}
        fontStyle="700"
        fill={color}
      />
    </Group>
  );
}

export function CockpitMap({
  robots,
  tasks,
  alerts,
  mode,
  zoom,
  resetKey,
  onZoomChange,
  onSelectionChange,
}: CockpitMapProps) {
  const { ref, size } = useContainerSize();
  const [stagePos, setStagePos] = useState({ x: 0, y: 0 });
  const [measurePoints, setMeasurePoints] = useState<Position[]>([]);

  useEffect(() => {
    setStagePos({ x: 0, y: 0 });
    setMeasurePoints([]);
  }, [resetKey]);

  const bounds = useMemo(() => collectBounds(robots, tasks, alerts), [robots, tasks, alerts]);
  const project = useMemo(
    () => createProjector(bounds, size.width, size.height),
    [bounds, size.width, size.height],
  );

  const robotPoints = useMemo(
    () =>
      robots
        .filter((r) => isPosition(r.position))
        .map((r) => ({ robot: r, point: project.toXY(r.position as Position) })),
    [robots, project],
  );

  const taskShapes = useMemo(
    () =>
      tasks.map((task) => ({
        task,
        center: project.toXY(task.target_area.center_point),
        radius: taskRadiusPixels(task, project),
        polygon: taskPolygon(task, project),
      })),
    [tasks, project],
  );

  const hazardAlerts = useMemo(
    () =>
      alerts
        .filter((a) => a.type.includes('fire') || yoloDetectionClass(a) === 'fire')
        .map((a) => {
          const pos = yoloDetectionPosition(a);
          return isPosition(pos) ? { alert: a, point: project.toXY(pos) } : null;
        })
        .filter((item): item is { alert: AlertRead; point: ProjectedPoint } => item !== null),
    [alerts, project],
  );

  const measureLine = useMemo(() => {
    if (measurePoints.length < 2) return null;
    const a = project.toXY(measurePoints[0]);
    const b = project.toXY(measurePoints[1]);
    return {
      points: [a.x, a.y, b.x, b.y],
      labelX: (a.x + b.x) / 2,
      labelY: (a.y + b.y) / 2,
      label: formatDistance(haversineMeters(measurePoints[0], measurePoints[1])),
    };
  }, [measurePoints, project]);

  const setZoomAroundPointer = (nextZoom: number, pointer: ProjectedPoint) => {
    const next = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
    const old = zoom;
    const mousePointTo = {
      x: (pointer.x - stagePos.x) / old,
      y: (pointer.y - stagePos.y) / old,
    };
    setStagePos({
      x: pointer.x - mousePointTo.x * next,
      y: pointer.y - mousePointTo.y * next,
    });
    onZoomChange(next);
  };

  return (
    <div ref={ref} className="h-full w-full">
      <Stage
        width={size.width}
        height={size.height}
        draggable={mode === 'pan'}
        x={stagePos.x}
        y={stagePos.y}
        scaleX={zoom}
        scaleY={zoom}
        onDragEnd={(e) => setStagePos({ x: e.target.x(), y: e.target.y() })}
        onWheel={(e) => {
          e.evt.preventDefault();
          const pointer = e.target.getStage()?.getPointerPosition();
          if (!pointer) return;
          const direction = e.evt.deltaY > 0 ? -1 : 1;
          setZoomAroundPointer(zoom + direction * 0.12, pointer);
        }}
        onClick={(e) => {
          if (mode !== 'measure' || e.target !== e.target.getStage()) return;
          const pointer = e.target.getStage()?.getPointerPosition();
          if (!pointer) return;
          const local = {
            x: (pointer.x - stagePos.x) / zoom,
            y: (pointer.y - stagePos.y) / zoom,
          };
          const pos = project.toPosition(local);
          setMeasurePoints((prev) => (prev.length >= 2 ? [pos] : [...prev, pos]));
        }}
      >
        <Layer>
          <Rect width={size.width} height={size.height} fill="#0F1419" />
          {Array.from({ length: Math.ceil(size.width / 48) + 2 }).map((_, i) => (
            <Line
              key={`v-${i}`}
              points={[i * 48, 0, i * 48, size.height]}
              stroke="#2A3142"
              strokeWidth={0.7}
              opacity={0.62}
            />
          ))}
          {Array.from({ length: Math.ceil(size.height / 48) + 2 }).map((_, i) => (
            <Line
              key={`h-${i}`}
              points={[0, i * 48, size.width, i * 48]}
              stroke="#2A3142"
              strokeWidth={0.7}
              opacity={0.62}
            />
          ))}

          {hazardAlerts.map(({ alert, point }) => (
            <Group key={alert.id} x={point.x} y={point.y}>
              <Circle radius={74} fillRadialGradientStartPoint={{ x: 0, y: 0 }} fillRadialGradientStartRadius={0} fillRadialGradientEndPoint={{ x: 0, y: 0 }} fillRadialGradientEndRadius={74} fillRadialGradientColorStops={[0, 'rgba(239,68,68,0.42)', 1, 'rgba(239,68,68,0)']} />
              <Text text="FIRE" x={-22} y={-5} width={44} align="center" fill="#EF4444" fontSize={10} fontStyle="700" />
            </Group>
          ))}

          {taskShapes.map(({ task, center, radius, polygon }) => {
            const color = TASK_COLORS[task.priority] ?? '#3B82F6';
            return (
              <Group
                key={task.id}
                onClick={() => {
                  onSelectionChange?.(`${task.code} · ${task.status} · ${Number(task.progress).toFixed(0)}%`);
                }}
                onTap={() => {
                  onSelectionChange?.(`${task.code} · ${task.status} · ${Number(task.progress).toFixed(0)}%`);
                }}
              >
                {polygon.length > 0 ? (
                  <Line points={polygon} closed stroke={color} strokeWidth={1.8} dash={[7, 5]} fill={`${color}1A`} />
                ) : (
                  <Circle x={center.x} y={center.y} radius={radius} stroke={color} strokeWidth={1.8} dash={[7, 5]} fill={`${color}1A`} />
                )}
                <Text
                  text={`${task.code} · ${Number(task.progress).toFixed(0)}%`}
                  x={center.x - 54}
                  y={center.y - radius - 18}
                  width={108}
                  align="center"
                  fontFamily="JetBrains Mono, monospace"
                  fontSize={10}
                  fontStyle="700"
                  fill={color}
                />
              </Group>
            );
          })}

          {robotPoints.map(({ robot, point }) => (
            <RobotMarker
              key={robot.id}
              robot={robot}
              point={point}
              onSelect={() => {
                onSelectionChange?.(
                  `${robot.code} · ${robot.fsm} · ${robot.battery.toFixed(0)}%`,
                );
              }}
            />
          ))}

          {measurePoints.map((pos, index) => {
            const p = project.toXY(pos);
            return <Circle key={`${pos.lat}-${pos.lng}-${index}`} x={p.x} y={p.y} radius={5} fill="#F59E0B" stroke="#111827" strokeWidth={2} />;
          })}
          {measureLine && (
            <Group>
              <Line points={measureLine.points} stroke="#F59E0B" strokeWidth={2} dash={[6, 6]} />
              <Rect x={measureLine.labelX - 38} y={measureLine.labelY - 13} width={76} height={24} cornerRadius={5} fill="rgba(17,24,39,0.92)" stroke="#F59E0B" strokeWidth={1} />
              <Text x={measureLine.labelX - 38} y={measureLine.labelY - 6} width={76} align="center" text={measureLine.label} fill="#F59E0B" fontSize={11} fontStyle="700" />
            </Group>
          )}

          <Group x={36} y={size.height - 42}>
            <Line points={[0, 0, 96, 0]} stroke="#5C6580" strokeWidth={2} />
            <Line points={[0, -4, 0, 4]} stroke="#5C6580" strokeWidth={2} />
            <Line points={[96, -4, 96, 4]} stroke="#5C6580" strokeWidth={2} />
            <Text text="100 m" x={23} y={10} fill="#5C6580" fontSize={10} />
          </Group>
        </Layer>
      </Stage>
    </div>
  );
}
