/**
 * Camera photos are the headline mobile flow, and raw phone photos break it twice:
 * they run 3–8 MB (over the API's 5 MB limit) and iPhones shoot HEIC (which the API
 * rejects with 415). Downscaling to a small JPEG fixes both at once — Safari decodes
 * HEIC natively, and the embedder downscales anyway so nothing is lost.
 *
 * Any failure returns the ORIGINAL file: this is an optimisation, never a gate.
 */

const MAX_EDGE_PX = 512;
const JPEG_QUALITY = 0.9;

export const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024; // mirrors the API's MAX_IMAGE_BYTES

export async function prepareImage(file: File): Promise<File> {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, MAX_EDGE_PX / Math.max(bitmap.width, bitmap.height));
    // Already small and of an accepted type: leave it untouched.
    if (scale === 1 && ACCEPTED_TYPES.includes(file.type) && file.size <= MAX_UPLOAD_BYTES) {
      bitmap.close();
      return file;
    }
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext('2d');
    if (!context) {
      bitmap.close();
      return file;
    }
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY),
    );
    if (!blob) return file;
    return new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', {
      type: 'image/jpeg',
    });
  } catch {
    return file;
  }
}

/** Returns a user-facing problem, or null if the file can be uploaded. */
export function validateImage(file: File): string | null {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return `${file.type || 'Ese tipo de archivo'} no está soportado — usa PNG, JPEG o WebP.`;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `La imagen pesa ${(file.size / 1024 / 1024).toFixed(1)} MB; el límite es 5 MB.`;
  }
  return null;
}
