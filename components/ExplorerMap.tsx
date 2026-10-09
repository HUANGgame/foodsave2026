"use client";

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import Map from "ol/Map.js";
import View from "ol/View.js";
import Overlay from "ol/Overlay.js";
import Feature from "ol/Feature.js";
import Point from "ol/geom/Point.js";
import TileLayer from "ol/layer/Tile.js";
import OSM from "ol/source/OSM.js";
import VectorSource from "ol/source/Vector.js";
import Cluster from "ol/source/Cluster.js";
import Attribution from "ol/control/Attribution.js";
import { defaults as defaultInteractions } from "ol/interaction/defaults.js";
import { fromLonLat, toLonLat } from "ol/proj.js";
import { unByKey } from "ol/Observable.js";
import type { Coordinate } from "ol/coordinate.js";
import Frog from "./Frog";
import "ol/ol.css";
import styles from "./ExplorerMap.module.css";

export type ExplorerStore = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  count: number | null;
  source: "foodsave" | "family";
};

type LatLng = [number, number];

export type ExplorerMapProps = {
  center: LatLng;
  devicePosition: LatLng | null;
  stores: ExplorerStore[];
  onSelect: (id: string) => void;
  onManualMove: () => void;
  onViewportCenter: (point: LatLng) => void;
  recenterVersion: number;
  heading: number | null;
  follow: boolean;
};

type Runtime = {
  map: Map;
  source: VectorSource<Feature<Point>>;
  clusters: Cluster<Feature<Point>>;
};

type MarkerGroup = {
  key: string;
  position: Coordinate;
  stores: ExplorerStore[];
};

const MAX_MERCATOR_LATITUDE = 85.0511287798;
const MIN_ZOOM = 3;
const MAX_ZOOM = 20;
const INITIAL_ZOOM = 15;

function projectPoint(point: LatLng | null): Coordinate | undefined {
  if (!point) return undefined;
  const [lat, lng] = point;
  if (
    !Number.isFinite(lat) ||
    !Number.isFinite(lng) ||
    Math.abs(lat) > MAX_MERCATOR_LATITUDE ||
    Math.abs(lng) > 180
  ) {
    return undefined;
  }
  return fromLonLat([lng, lat]);
}

function normalizedDegrees(degrees: number): number {
  return ((degrees % 360) + 360) % 360;
}

function duration(): number {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ? 0
    : 180;
}

function stockLabel(store: ExplorerStore): string {
  if (store.count === null || !Number.isFinite(store.count)) {
    return "庫存未知";
  }
  const count = Math.max(0, store.count);
  return store.source === "foodsave"
    ? String(count) + " 項商品"
    : String(count) + " 份（來源回報）";
}

function stockBadge(store: ExplorerStore): string {
  if (store.count === null || !Number.isFinite(store.count)) return "?";
  return String(Math.max(0, store.count));
}

function OverlayPortal({
  map,
  position,
  className,
  passive = false,
  children,
}: {
  map: Map;
  position: Coordinate | undefined;
  className: string;
  passive?: boolean;
  children: ReactNode;
}) {
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  const overlayRef = useRef<Overlay | null>(null);
  const x = position?.[0];
  const y = position?.[1];

  useEffect(() => {
    const element = document.createElement("div");
    element.className = styles.portalHost;
    const overlay = new Overlay({
      element,
      positioning: "center-center",
      stopEvent: true,
      insertFirst: false,
      autoPan: false,
      className: [
        styles.overlay,
        className,
        passive ? styles.passiveOverlay : "",
      ]
        .filter(Boolean)
        .join(" "),
    });
    overlayRef.current = overlay;
    map.addOverlay(overlay);
    setHost(element);

    return () => {
      overlayRef.current = null;
      map.removeOverlay(overlay);
      overlay.dispose();
    };
  }, [map, className, passive]);

  useEffect(() => {
    overlayRef.current?.setPosition(
      x === undefined || y === undefined ? undefined : [x, y],
    );
  }, [map, className, passive, x, y]);

  return host ? createPortal(children, host) : null;
}

export default function ExplorerMap(props: ExplorerMapProps) {
  const {
    center,
    devicePosition,
    stores,
    follow,
    heading,
    recenterVersion,
  } = props;

  const targetRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const initialRef = useRef(props);
  const latestRef = useRef(props);
  const manualStoppedRef = useRef(!follow);
  const lastCenterRef = useRef(String(center[0]) + "," + String(center[1]));
  const lastRecenterRef = useRef(recenterVersion);
  const groupSignatureRef = useRef("");
  const returnFocusRef = useRef<HTMLButtonElement | null>(null);
  const chooserRef = useRef<HTMLDivElement | null>(null);

  const [runtime, setRuntime] = useState<Runtime | null>(null);
  const [groups, setGroups] = useState<MarkerGroup[]>([]);
  const [expandedIds, setExpandedIds] = useState<string[]>([]);
  const [rotation, setRotation] = useState(0);
  const [zoom, setZoom] = useState(INITIAL_ZOOM);
  const [headingMode, setHeadingMode] = useState(false);
  const [tileError, setTileError] = useState(false);

  const instructionsId = useId();
  const chooserTitleId = useId();
  const centerLat = center[0];
  const centerLng = center[1];
  const deviceLat = devicePosition?.[0];
  const deviceLng = devicePosition?.[1];
  const queryPosition = projectPoint(center);
  const gpsPosition = projectPoint(devicePosition);
  const headingAvailable = heading !== null && Number.isFinite(heading);
  const rotationDegrees = normalizedDegrees((rotation * 180) / Math.PI);

  useEffect(() => {
    latestRef.current = props;
  }, [props]);

  const markManualMove = useCallback(() => {
    manualStoppedRef.current = true;
    mapRef.current?.getView().cancelAnimations();
    setHeadingMode(false);
    latestRef.current.onManualMove();
  }, []);

  useEffect(() => {
    const target = targetRef.current;
    if (!target) return;
    const initial = initialRef.current;
    const initialPosition =
      (initial.follow ? projectPoint(initial.devicePosition) : undefined) ??
      projectPoint(initial.center) ??
      [0, 0];

    const source = new VectorSource<Feature<Point>>({ wrapX: false });
    const clusters = new Cluster<Feature<Point>>({
      source,
      distance: 56,
      minDistance: 0,
      wrapX: false,
    });
    const osm = new OSM();
    const tileErrorKey = osm.on("tileloaderror", () => setTileError(true));

    const map = new Map({
      target,
      layers: [new TileLayer({ source: osm })],
      controls: [new Attribution({ collapsible: false })],
      interactions: defaultInteractions({
        altShiftDragRotate: true,
        pinchRotate: true,
        pinchZoom: true,
        dragPan: true,
        keyboard: true,
        mouseWheelZoom: true,
      }),
      view: new View({
        center: initialPosition,
        zoom: INITIAL_ZOOM,
        minZoom: MIN_ZOOM,
        maxZoom: MAX_ZOOM,
        enableRotation: true,
        constrainRotation: false,
        multiWorld: false,
      }),
    });

    mapRef.current = map;
    const resizeObserver = new ResizeObserver(() => map.updateSize());
    resizeObserver.observe(target);
    setRuntime({ map, source, clusters });

    return () => {
      if (mapRef.current === map) mapRef.current = null;
      resizeObserver.disconnect();
      unByKey(tileErrorKey);
      clusters.setSource(null);
      clusters.dispose();
      source.dispose();
      map.setTarget(undefined);
      map.dispose();
      osm.dispose();
    };
  }, []);

  const syncGroups = useCallback(() => {
    if (!runtime) return;
    const { map, clusters } = runtime;
    const view = map.getView();
    const size = map.getSize();
    const resolution = view.getResolution();
    if (
      !size ||
      size[0] <= 0 ||
      size[1] <= 0 ||
      resolution === undefined
    ) {
      return;
    }

    clusters.loadFeatures(
      view.calculateExtent(size),
      resolution,
      view.getProjection(),
    );

    const next: MarkerGroup[] = [];
    for (const feature of clusters.getFeatures()) {
      const geometry = feature.getGeometry();
      if (!(geometry instanceof Point)) continue;
      const position = geometry.getCoordinates();
      const pixel = map.getPixelFromCoordinate(position);
      if (!pixel) continue;

      const margin = 40;
      if (
        pixel[0] < -margin ||
        pixel[1] < -margin ||
        pixel[0] > size[0] + margin ||
        pixel[1] > size[1] + margin
      ) {
        continue;
      }

      const members = feature.get("features") as
        | Feature<Point>[]
        | undefined;
      const groupStores = (members ?? [])
        .map((member) => member.get("store") as ExplorerStore | undefined)
        .filter((store): store is ExplorerStore => Boolean(store))
        .sort((a, b) => a.id.localeCompare(b.id));

      if (!groupStores.length) continue;
      next.push({
        key: JSON.stringify(groupStores.map((store) => store.id)),
        position,
        stores: groupStores,
      });
    }

    next.sort((a, b) => a.key.localeCompare(b.key));
    const signature = JSON.stringify(next);
    if (signature !== groupSignatureRef.current) {
      groupSignatureRef.current = signature;
      setGroups(next);
    }
  }, [runtime]);

  useEffect(() => {
    if (!runtime) return;
    const features = [...stores]
      .sort((a, b) => a.id.localeCompare(b.id))
      .flatMap((store) => {
        const position = projectPoint([store.lat, store.lng]);
        if (!position) return [];
        const feature = new Feature<Point>({
          geometry: new Point(position),
          store,
        });
        feature.setId(store.id);
        return [feature];
      });

    runtime.source.clear(true);
    runtime.source.addFeatures(features);
    syncGroups();
  }, [runtime, stores, syncGroups]);

  useEffect(() => {
    if (!runtime) return;
    const { map } = runtime;
    const view = map.getView();
    let frame: number | null = null;
    let centerTimer: ReturnType<typeof setTimeout> | undefined;

    const scheduleGroups = () => {
      if (frame !== null) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        syncGroups();
      });
    };
    const syncViewState = () => {
      setRotation(view.getRotation());
      setZoom(view.getZoom() ?? INITIAL_ZOOM);
      scheduleGroups();
    };
    const reportViewport = () => {
      if (centerTimer !== undefined) clearTimeout(centerTimer);
      centerTimer = setTimeout(() => {
        const coordinate = view.getCenter();
        if (!coordinate) return;
        const [lng, lat] = toLonLat(coordinate);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
        latestRef.current.onViewportCenter([lat, lng]);
      }, 140);
    };
    const onMoveEnd = () => {
      scheduleGroups();
      reportViewport();
    };
    const keys = [
      view.on("change:resolution", syncViewState),
      view.on("change:rotation", syncViewState),
      map.on("moveend", onMoveEnd),
      map.on("change:size", scheduleGroups),
      map.once("postrender", scheduleGroups),
    ];

    syncViewState();
    reportViewport();
    return () => {
      unByKey(keys);
      if (frame !== null) cancelAnimationFrame(frame);
      if (centerTimer !== undefined) clearTimeout(centerTimer);
    };
  }, [runtime, syncGroups]);

  useEffect(() => {
    if (!runtime) return;
    const target = targetRef.current;
    if (!target) return;
    const keys = [
      runtime.map.on("pointerdrag", markManualMove),
      runtime.map.on("dblclick", markManualMove),
    ];
    const onWheel = () => markManualMove();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.target !== target) return;
      if (
        [
          "ArrowUp",
          "ArrowDown",
          "ArrowLeft",
          "ArrowRight",
          "+",
          "-",
          "=",
        ].includes(event.key)
      ) {
        markManualMove();
      }
    };
    target.addEventListener("wheel", onWheel, {
      passive: true,
      capture: true,
    });
    target.addEventListener("keydown", onKeyDown, true);

    return () => {
      unByKey(keys);
      target.removeEventListener("wheel", onWheel, true);
      target.removeEventListener("keydown", onKeyDown, true);
    };
  }, [runtime, markManualMove]);

  useEffect(() => {
    manualStoppedRef.current = !follow;
    if (!follow) setHeadingMode(false);
  }, [follow, recenterVersion]);

  useEffect(() => {
    if (!runtime) return;
    const key = String(centerLat) + "," + String(centerLng);
    if (key === lastCenterRef.current) return;
    lastCenterRef.current = key;
    const position = projectPoint([centerLat, centerLng]);
    if (position) runtime.map.getView().setCenter(position);
  }, [runtime, centerLat, centerLng]);

  useEffect(() => {
    if (!runtime || recenterVersion === lastRecenterRef.current) return;
    lastRecenterRef.current = recenterVersion;
    const current = latestRef.current;
    const position =
      (current.follow ? projectPoint(current.devicePosition) : undefined) ??
      projectPoint(current.center);
    if (position) runtime.map.getView().setCenter(position);
  }, [runtime, recenterVersion]);

  useEffect(() => {
    if (
      !runtime ||
      !follow ||
      manualStoppedRef.current ||
      deviceLat === undefined ||
      deviceLng === undefined
    ) {
      return;
    }
    const position = projectPoint([deviceLat, deviceLng]);
    if (!position) return;
    const view = runtime.map.getView();
    const current = view.getCenter();
    const nextRotation =
      headingMode && heading !== null && Number.isFinite(heading)
        ? (-normalizedDegrees(heading) * Math.PI) / 180
        : view.getRotation();

    const centerChanged =
      !current ||
      Math.abs(current[0] - position[0]) > 0.01 ||
      Math.abs(current[1] - position[1]) > 0.01;
    const angularDifference = Math.atan2(
      Math.sin(nextRotation - view.getRotation()),
      Math.cos(nextRotation - view.getRotation()),
    );
    if (!centerChanged && Math.abs(angularDifference) < 0.000001) return;

    view.animate({
      center: position,
      rotation: nextRotation,
      duration: duration(),
    });
  }, [
    runtime,
    follow,
    deviceLat,
    deviceLng,
    heading,
    headingMode,
    recenterVersion,
  ]);

  const expandedStores = useMemo(() => {
    const ids = new Set(expandedIds);
    return stores
      .filter((store) => ids.has(store.id))
      .sort((a, b) => a.name.localeCompare(b.name, "zh-Hant"));
  }, [expandedIds, stores]);

  const closeChooser = useCallback(() => {
    setExpandedIds([]);
    const trigger = returnFocusRef.current;
    if (trigger?.isConnected) trigger.focus();
    else targetRef.current?.focus();
  }, []);

  useEffect(() => {
    if (expandedIds.length && !expandedStores.length) closeChooser();
  }, [expandedIds.length, expandedStores.length, closeChooser]);

  useEffect(() => {
    if (!expandedIds.length) return;
    chooserRef.current
      ?.querySelector<HTMLButtonElement>("button[data-store-choice]")
      ?.focus();
  }, [expandedIds]);

  function rotateBy(delta: number) {
    if (!runtime) return;
    markManualMove();
    const view = runtime.map.getView();
    view.animate({
      rotation: view.getRotation() + delta,
      duration: duration(),
    });
  }

  function faceNorth() {
    if (!runtime) return;
    markManualMove();
    runtime.map.getView().animate({ rotation: 0, duration: duration() });
  }

  function zoomBy(delta: number) {
    if (!runtime) return;
    markManualMove();
    const view = runtime.map.getView();
    view.animate({
      zoom: Math.min(
        MAX_ZOOM,
        Math.max(MIN_ZOOM, (view.getZoom() ?? INITIAL_ZOOM) + delta),
      ),
      duration: duration(),
    });
  }

  function selectStore(id: string) {
    setExpandedIds([]);
    latestRef.current.onSelect(id);
  }

  return (
    <div
      className={styles.root}
      role="region"
      aria-label="附近店家探索地圖"
      data-testid="explorer-map"
      data-rotation={Math.round(rotationDegrees * 1000) / 1000}
      onKeyDown={(event) => {
        if (event.key === "Escape" && expandedIds.length) {
          event.preventDefault();
          event.stopPropagation();
          closeChooser();
        }
      }}
    >
      <div
        ref={targetRef}
        className={styles.map}
        tabIndex={0}
        aria-label="店家地圖"
        aria-describedby={instructionsId}
        data-testid="explorer-map-surface"
      />

      <p id={instructionsId} className={styles.srOnly}>
        拖曳或使用方向鍵移動地圖，以加減鍵縮放。觸控可用雙指縮放與旋轉。
        桌面可按住 Alt 與 Shift 拖曳旋轉，也可使用旋轉按鈕。
        虛線圓圈是搜尋中心，青蛙是目前定位位置。
      </p>

      {tileError && (
        <p
          className={styles.tileStatus}
          role="status"
          data-testid="explorer-map-tile-error"
        >
          部分底圖載入失敗，仍可選擇店家；也可以重新整理再試。
        </p>
      )}

      {runtime && (
        <>
          <OverlayPortal
            map={runtime.map}
            position={queryPosition}
            className={styles.queryOverlay}
            passive
          >
            <div
              className={styles.queryMarker}
              role="img"
              aria-label="搜尋中心"
              data-testid="explorer-query-center"
            />
          </OverlayPortal>

          {groups.map((group) => {
            const store = group.stores[0];
            return (
              <OverlayPortal
                key={group.key}
                map={runtime.map}
                position={group.position}
                className={styles.merchantOverlay}
              >
                {group.stores.length === 1 ? (
                  <button
                    type="button"
                    className={[
                      styles.storeMarker,
                      store.source === "family"
                        ? styles.familyMarker
                        : styles.foodsaveMarker,
                      store.count === 0 ? styles.emptyMarker : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    aria-label={"選擇店家：" + store.name}
                    title={store.name + " · " + stockLabel(store)}
                    data-testid={"explorer-store-" + store.id}
                    onClick={() => selectStore(store.id)}
                  >
                    <span aria-hidden="true">
                      {store.source === "family" ? "全" : "惜"}
                    </span>
                    <span className={styles.stockBadge} aria-hidden="true">
                      {stockBadge(store)}
                    </span>
                  </button>
                ) : (
                  <button
                    type="button"
                    className={styles.clusterMarker}
                    aria-label={"展開附近 " + String(group.stores.length) + " 間店家"}
                    aria-expanded={group.stores.every((member) =>
                      expandedIds.includes(member.id),
                    )}
                    data-testid="explorer-cluster"
                    onClick={(event) => {
                      returnFocusRef.current = event.currentTarget;
                      setExpandedIds(group.stores.map((member) => member.id));
                    }}
                  >
                    <span aria-hidden="true">{group.stores.length}</span>
                    <span className={styles.clusterUnit} aria-hidden="true">
                      間
                    </span>
                  </button>
                )}
              </OverlayPortal>
            );
          })}

          {gpsPosition && (
            <OverlayPortal
              map={runtime.map}
              position={gpsPosition}
              className={styles.frogOverlay}
              passive
            >
              <div
                className={styles.frogBody}
                role="img"
                aria-label="目前定位位置"
                data-testid="explorer-device-position"
              >
                <div aria-hidden="true">
                  <Frog />
                </div>
              </div>
            </OverlayPortal>
          )}
        </>
      )}

      <div className={styles.controls} aria-label="地圖操作">
        <div className={styles.rotationControls}>
          <button
            type="button"
            className={styles.controlButton}
            aria-label="向左旋轉地圖"
            title="向左旋轉 45°"
            disabled={!runtime}
            onClick={() => rotateBy(-Math.PI / 4)}
          >
            <span aria-hidden="true">↶</span>
          </button>
          <button
            type="button"
            className={styles.controlButton + " " + styles.northButton}
            aria-label="地圖朝北"
            title="地圖朝北"
            disabled={!runtime}
            onClick={faceNorth}
          >
            <span
              className={styles.northNeedle}
              style={{ transform: "rotate(" + String(rotationDegrees) + "deg)" }}
              aria-hidden="true"
            >
              ↑
            </span>
            <span className={styles.northLetter} aria-hidden="true">
              N
            </span>
          </button>
          <button
            type="button"
            className={styles.controlButton}
            aria-label="向右旋轉地圖"
            title="向右旋轉 45°"
            disabled={!runtime}
            onClick={() => rotateBy(Math.PI / 4)}
          >
            <span aria-hidden="true">↷</span>
          </button>
        </div>

        <div className={styles.zoomControls}>
          <button
            type="button"
            className={styles.controlButton}
            aria-label="放大地圖"
            disabled={!runtime || zoom >= MAX_ZOOM}
            onClick={() => zoomBy(1)}
          >
            <span aria-hidden="true">+</span>
          </button>
          <button
            type="button"
            className={styles.controlButton}
            aria-label="縮小地圖"
            disabled={!runtime || zoom <= MIN_ZOOM}
            onClick={() => zoomBy(-1)}
          >
            <span aria-hidden="true">−</span>
          </button>
        </div>

        <button
          type="button"
          className={styles.headingButton}
          aria-label="依 GPS 移動方向旋轉地圖"
          aria-pressed={headingMode && follow}
          disabled={!runtime || !follow || !headingAvailable}
          title={
            !follow
              ? "先開啟跟隨定位"
              : !headingAvailable
                ? "目前沒有 GPS 移動方向"
                : "依 GPS 移動方向朝上，並非手機朝向"
          }
          onClick={() => setHeadingMode((enabled) => !enabled)}
        >
          移動方向朝上
        </button>

        <output
          className={styles.rotationValue}
          aria-label="地圖旋轉角度"
          data-testid="explorer-rotation"
        >
          {Math.round(rotationDegrees) % 360}°
        </output>
      </div>

      {expandedStores.length > 0 && (
        <div
          ref={chooserRef}
          className={styles.clusterPanel}
          role="region"
          aria-labelledby={chooserTitleId}
          data-testid="explorer-cluster-list"
        >
          <div className={styles.clusterHeader}>
            <h3 id={chooserTitleId}>
              附近 {expandedStores.length} 間店家
            </h3>
            <button
              type="button"
              className={styles.closeButton}
              aria-label="關閉店家清單"
              onClick={closeChooser}
            >
              <span aria-hidden="true">×</span>
            </button>
          </div>
          <ul className={styles.clusterList}>
            {expandedStores.map((store) => (
              <li key={store.id}>
                <button
                  type="button"
                  className={styles.storeChoice}
                  aria-label={"選擇店家：" + store.name}
                  data-testid={"explorer-store-" + store.id}
                  data-store-choice
                  onClick={() => selectStore(store.id)}
                >
                  <span className={styles.choiceName}>{store.name}</span>
                  <span className={styles.choiceStock}>
                    {stockLabel(store)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
