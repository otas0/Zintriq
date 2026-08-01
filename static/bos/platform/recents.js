const RECENTS_KEY = "bos-object-recents";
const FAVORITES_KEY = "bos-object-favorites";

/** @typedef {{ collection: string, id: string, label: string, at: string }} ObjectRecent */

function loadRecents() {
  try {
    return JSON.parse(localStorage.getItem(RECENTS_KEY) || "[]");
  } catch {
    return [];
  }
}

function loadFavorites() {
  try {
    return new Set(JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

/** @type {ObjectRecent[]} */
let objectRecents = loadRecents();
/** @type {Set<string>} */
let objectFavorites = loadFavorites();

/** @type {Set<() => void>} */
const listeners = new Set();

function notify() {
  listeners.forEach((fn) => fn());
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function trackObjectRecent(collection, id, label) {
  objectRecents = [
    { collection, id, label, at: new Date().toISOString() },
    ...objectRecents.filter((r) => !(r.collection === collection && r.id === id)),
  ].slice(0, 20);
  localStorage.setItem(RECENTS_KEY, JSON.stringify(objectRecents));
  notify();
}

export function getObjectRecents() {
  return [...objectRecents];
}

export function isObjectFavorite(collection, id) {
  return objectFavorites.has(`${collection}:${id}`);
}

export function toggleObjectFavorite(collection, id, label) {
  const key = `${collection}:${id}`;
  if (objectFavorites.has(key)) objectFavorites.delete(key);
  else objectFavorites.add(key);
  localStorage.setItem(FAVORITES_KEY, JSON.stringify([...objectFavorites]));
  if (label) trackObjectRecent(collection, id, label);
  notify();
  return objectFavorites.has(key);
}

export function getObjectFavorites() {
  return [...objectFavorites].map((key) => {
    const [collection, id] = key.split(":");
    const recent = objectRecents.find((r) => r.collection === collection && r.id === id);
    return { collection, id, label: recent?.label || id };
  });
}

export function objectRef(collection, id) {
  return `${collection}:${id}`;
}
