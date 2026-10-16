"""Optional later rally contact from public camera fits; no action selection."""
import builtin_players as public


class RallyLatePlayer(public.Player):
    def predict(self):
        # Preserve every service phase and its existing late-contact semantics.
        if self.leg['kind'] not in ("opponent's return", 'return'):
            return super().predict()
        frames = sorted(self.leg['frames'].items())
        own = self._bounce_t('own')
        before = [(t, x) for t, x in frames if t > 0 and (own is None or t < own - .003)]
        fit = public.fit_flight(before, fit_accel=True) if len(before) >= 3 else None
        if own is not None:
            after = [(t, x) for t, x in frames if t > own + .003]
            if len(after) >= 3:
                post = public.fit_flight(after, a_fixed=None if fit is None else fit[3])
                contact = public.predict_contact(*post[:4], need_bounce=False, late=True)
                if contact is not None:
                    return contact + ('post', len(after))
        if fit is None:
            return None
        contact = public.predict_contact(*fit[:4], need_bounce=own is None, late=True)
        return None if contact is None else contact + ('pre', len(before))
