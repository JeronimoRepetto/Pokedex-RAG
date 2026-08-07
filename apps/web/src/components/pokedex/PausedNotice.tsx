'use client';

/**
 * Shown on the device's screen when the API reports itself switched off.
 *
 * Bilingual by design rather than by locale detection: the demo's audience is mixed and
 * a visitor should never have to guess which half applies to them. This is deliberately
 * NOT the same as the "cannot reach the API" error — being paused on purpose and being
 * broken are different facts, and conflating them would make a working demo look dead.
 */
export function PausedNotice({ contact }: { contact: string }) {
  return (
    <div className="screen-content paused-notice">
      <p className="paused-heading">Servicio pausado</p>
      <p>
        Esta demo está apagada para que no genere coste mientras nadie la usa.
        {contact
          ? ` Escribí a ${contact} para activarla.`
          : ' Pedile al desarrollador que la active.'}
      </p>
      <hr />
      <p className="paused-heading">Service paused</p>
      <p>
        This demo is switched off so it costs nothing while idle.
        {contact ? ` Contact ${contact} to turn it on.` : ' Ask the developer to switch it on.'}
      </p>
    </div>
  );
}
