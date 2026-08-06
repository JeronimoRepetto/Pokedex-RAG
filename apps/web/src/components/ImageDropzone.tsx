'use client';

import { useRef, useState } from 'react';

const ACCEPTED = ['image/png', 'image/jpeg', 'image/webp'];
const MAX_BYTES = 5 * 1024 * 1024; // mirrors the API's own limit

/**
 * Drop-zone that validates before uploading. The API enforces the same type/size rules
 * and would answer 415/413, but rejecting locally saves a round trip and gives an
 * instant, specific message.
 */
export function ImageDropzone({
  onFile,
  disabled,
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function accept(file: File | undefined) {
    if (!file) return;
    if (!ACCEPTED.includes(file.type)) {
      setLocalError(
        `${file.type || 'That file type'} is not supported — use PNG, JPEG or WebP.`,
      );
      return;
    }
    if (file.size > MAX_BYTES) {
      setLocalError(
        `That image is ${(file.size / 1024 / 1024).toFixed(1)} MB; the limit is 5 MB.`,
      );
      return;
    }
    setLocalError(null);
    onFile(file);
  }

  return (
    <div className="stack">
      {/* A real <button> rather than a div with role="button": keyboard activation,
          focus handling and the disabled state all come for free and correct. */}
      <button
        type="button"
        className={`dropzone${dragging ? ' dragging' : ''}`}
        aria-label="Search by image: drop a sprite here or activate to choose a file"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!disabled) accept(event.dataTransfer.files?.[0]);
        }}
      >
        Drop a Pokémon sprite here, or click to choose one
        <span className="muted" style={{ display: 'block', marginTop: '0.3rem' }}>
          PNG, JPEG or WebP · up to 5 MB · matched against sprite vectors
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED.join(',')}
        hidden
        data-testid="image-input"
        onChange={(event) => accept(event.target.files?.[0])}
      />
      {localError ? (
        <div className="alert" role="alert">
          {localError}
        </div>
      ) : null}
    </div>
  );
}
