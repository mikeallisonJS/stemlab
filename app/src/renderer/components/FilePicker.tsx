import { useEffect, useState } from "react";

import { api } from "../api";
import type { FsListing } from "../types";

interface Props {
  title: string;
  /** "files" picks audio files (several), "folder" picks the folder being shown */
  mode: "files" | "folder";
  start?: string;
  onPick: (paths: string[]) => void;
  onClose: () => void;
}

/**
 * Browses folders on the machine the server runs on. A web page cannot learn
 * the path of a file picked through the browser's own dialog, and the engine
 * works on paths.
 */
export function FilePicker({ title, mode, start, onPick, onClose }: Props) {
  const [listing, setListing] = useState<FsListing | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [typed, setTyped] = useState(start ?? "");

  const open = (path?: string) => {
    api
      .browse(path)
      .then((result) => {
        setListing(result);
        setTyped(result.path ?? "");
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  };

  useEffect(() => {
    api
      .browse(start)
      .then(setListing)
      .catch(() => open());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = (path: string) => {
    const next = new Set(picked);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setPicked(next);
  };

  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal picker" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
        <h3>{title}</h3>
        <form className="path-row" onSubmit={(e) => {
          e.preventDefault();
          open(typed || undefined);
        }}>
          <button type="button" disabled={!listing?.path} onClick={() => open(listing?.parent ?? undefined)}>Up</button>
          <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type or paste a folder path" aria-label="Folder path" />
          <button type="submit">Go</button>
        </form>
        {error && <div className="banner error">{error}</div>}
        <div className="listing">
          {listing?.folders.map((folder) => (
            <div key={folder.path} className="entry folder" onDoubleClick={() => open(folder.path)} onClick={() => open(folder.path)}>
              📁 {folder.name}
            </div>
          ))}
          {mode === "files" && listing?.files.map((file) => (
            <label key={file.path} className={`entry file${picked.has(file.path) ? " picked" : ""}`}>
              <input type="checkbox" checked={picked.has(file.path)} onChange={() => toggle(file.path)} />
              {file.name}
              <span className="muted">{(file.size / 1048576).toFixed(1)} MB</span>
            </label>
          ))}
          {listing && !listing.folders.length && (mode === "folder" || !listing.files.length) && (
            <p className="muted">{mode === "files" ? "No audio files here." : "No subfolders."}</p>
          )}
        </div>
        <div className="modal-buttons">
          <span className="muted">{mode === "files" ? `${picked.size} selected` : listing?.path}</span>
          <span className="spacer" />
          <button onClick={onClose}>Cancel</button>
          {mode === "files" ? (
            <button className="primary" disabled={!picked.size} onClick={() => onPick([...picked])}>Add</button>
          ) : (
            <button className="primary" disabled={!listing?.path} onClick={() => listing?.path && onPick([listing.path])}>Use this folder</button>
          )}
        </div>
      </div>
    </div>
  );
}
