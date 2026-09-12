const MANIFEST_URL = "assets/videos/gallery_manifest.json";

const gallery = document.getElementById("videoGallery");
const statusEl = document.getElementById("galleryStatus");
const sensorFilter = document.getElementById("sensorFilter");
const sceneFilter = document.getElementById("sceneFilter");
const taskFilter = document.getElementById("taskFilter");
const resetButton = document.getElementById("resetFilters");

let records = [];
let observer = null;

function uniqueOptions(items, key, labelKey) {
  const map = new Map();
  items.forEach((item) => {
    if (!map.has(item[key])) {
      map.set(item[key], item[labelKey]);
    }
  });
  return [...map.entries()].sort((a, b) => a[1].localeCompare(b[1]));
}

function fillSelect(select, options) {
  const first = select.options[0];
  select.replaceChildren(first);
  options.forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.appendChild(option);
  });
}

function createCard(record) {
  const article = document.createElement("article");
  article.className = "video-card";
  article.dataset.sensor = record.sensor_slug;
  article.dataset.scene = record.scene_slug;
  article.dataset.task = record.task_slug;

  const videoWrap = document.createElement("div");
  videoWrap.className = "video-frame";

  const video = document.createElement("video");
  video.muted = true;
  video.loop = true;
  video.playsInline = true;
  video.preload = "metadata";
  video.poster = record.poster;
  video.setAttribute("aria-label", `${record.task_label}, ${record.scene_label}, ${record.sensor_label}`);

  const source = document.createElement("source");
  source.src = record.video;
  source.type = "video/mp4";
  video.appendChild(source);
  videoWrap.appendChild(video);

  const body = document.createElement("div");
  body.className = "video-card-body";

  const title = document.createElement("h3");
  title.textContent = record.task_label;

  const meta = document.createElement("p");
  meta.textContent = `${record.scene_label} · ${record.sensor_label}`;

  const stream = document.createElement("span");
  stream.className = "stream-label";
  stream.textContent = record.stream_label;

  body.append(title, meta, stream);
  article.append(videoWrap, body);
  return article;
}

function setupObserver() {
  if (observer) {
    observer.disconnect();
  }
  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const video = entry.target;
        if (entry.isIntersecting) {
          video.play().catch(() => {});
        } else {
          video.pause();
        }
      });
    },
    { threshold: 0.28, rootMargin: "120px 0px" }
  );
  document.querySelectorAll(".video-card video").forEach((video) => observer.observe(video));
}

function activeRecords() {
  const sensor = sensorFilter.value;
  const scene = sceneFilter.value;
  const task = taskFilter.value;
  return records.filter((record) => {
    return (
      (sensor === "all" || record.sensor_slug === sensor) &&
      (scene === "all" || record.scene_slug === scene) &&
      (task === "all" || record.task_slug === task)
    );
  });
}

function render() {
  const filtered = activeRecords();
  gallery.replaceChildren(...filtered.map(createCard));
  statusEl.textContent = `${filtered.length} clips shown from ${records.length} synchronized preview clips.`;
  setupObserver();
}

function initFilters() {
  fillSelect(sensorFilter, uniqueOptions(records, "sensor_slug", "sensor_label"));
  fillSelect(sceneFilter, uniqueOptions(records, "scene_slug", "scene_label"));
  fillSelect(taskFilter, uniqueOptions(records, "task_slug", "task_label"));
  [sensorFilter, sceneFilter, taskFilter].forEach((select) => select.addEventListener("change", render));
  resetButton.addEventListener("click", () => {
    sensorFilter.value = "all";
    sceneFilter.value = "all";
    taskFilter.value = "all";
    render();
  });
}

fetch(MANIFEST_URL)
  .then((response) => {
    if (!response.ok) {
      throw new Error(`Failed to load ${MANIFEST_URL}`);
    }
    return response.json();
  })
  .then((data) => {
    records = data;
    initFilters();
    render();
  })
  .catch((error) => {
    statusEl.textContent = "Video gallery failed to load. Please check the local manifest.";
    console.error(error);
  });
