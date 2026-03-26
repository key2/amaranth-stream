"""Extended stream Signature and Interface for amaranth-stream.

This module provides a ``Signature`` class (a ``wiring.Signature`` subclass) that extends
Amaranth's built-in stream with optional ``first``, ``last``, ``param``, and ``keep`` members.
The built-in ``amaranth.lib.stream.Signature`` is ``@final`` and cannot be subclassed, so we
implement a parallel hierarchy.
"""

import math

from amaranth.hdl import Shape, ShapeLike, Signal, Const
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out


__all__ = ["Signature", "Interface", "core_to_extended", "connect_streams"]


class Signature(wiring.Signature):
    """Extended stream signature with optional first/last, param, keep.

    Parameters
    ----------
    payload_shape : :class:`~.hdl.ShapeLike`
        Shape of the payload member.
    always_valid : :class:`bool`
        Whether the stream always has a valid payload (``valid`` driven to ``Const(1)``
        in the created :class:`Interface`).
    always_ready : :class:`bool`
        Whether the stream is always ready (``ready`` driven to ``Const(1)``
        in the created :class:`Interface`).
    has_first_last : :class:`bool`
        If ``True``, adds ``first`` and ``last`` members for packet framing.
    param_shape : :class:`~.hdl.ShapeLike` or ``None``
        If not ``None``, adds a ``param`` sideband member with the given shape.
    has_keep : :class:`bool`
        If ``True``, adds a ``keep`` member whose width is ``ceil(payload_width / 8)``.

    Members
    -------
    payload : :py:`Out(payload_shape)`
        Payload data.
    valid : :py:`Out(1)`
        Whether a payload is available.
    ready : :py:`In(1)`
        Whether a payload is accepted.
    first : :py:`Out(1)` *(only if has_first_last)*
        Marks the first beat of a packet.
    last : :py:`Out(1)` *(only if has_first_last)*
        Marks the last beat of a packet.
    param : :py:`Out(param_shape)` *(only if param_shape is not None)*
        Sideband parameter.
    keep : :py:`Out(keep_width)` *(only if has_keep)*
        Byte-enable mask.
    """

    def __init__(self, payload_shape, *,
                 always_valid=False, always_ready=False,
                 has_first_last=False, param_shape=None, has_keep=False):
        Shape.cast(payload_shape)
        self._payload_shape = payload_shape
        self._always_valid = bool(always_valid)
        self._always_ready = bool(always_ready)
        self._has_first_last = bool(has_first_last)
        self._param_shape = param_shape
        self._has_keep = bool(has_keep)

        members = {}
        members["payload"] = Out(payload_shape)
        members["valid"] = Out(1)
        members["ready"] = In(1)

        if has_first_last:
            members["first"] = Out(1)
            members["last"] = Out(1)

        if param_shape is not None:
            Shape.cast(param_shape)
            members["param"] = Out(param_shape)

        if has_keep:
            shape = Shape.cast(payload_shape)
            keep_width = max(1, math.ceil(shape.width / 8))
            members["keep"] = Out(keep_width)

        super().__init__(members)

    # -- Properties ----------------------------------------------------------

    @property
    def payload_shape(self):
        """The shape of the payload member."""
        return self._payload_shape

    @property
    def always_valid(self):
        """Whether the stream always has a valid payload."""
        return self._always_valid

    @property
    def always_ready(self):
        """Whether the stream is always ready."""
        return self._always_ready

    @property
    def has_first_last(self):
        """Whether the stream has ``first`` and ``last`` framing members."""
        return self._has_first_last

    @property
    def param_shape(self):
        """The shape of the ``param`` member, or ``None``."""
        return self._param_shape

    @property
    def has_keep(self):
        """Whether the stream has a ``keep`` byte-enable member."""
        return self._has_keep

    @property
    def payload_width(self):
        """The bit-width of the payload."""
        return Shape.cast(self._payload_shape).width

    # -- Signature protocol --------------------------------------------------

    def create(self, *, path=None, src_loc_at=0):
        """Create an :class:`Interface` from this signature."""
        return Interface(self, path=path, src_loc_at=1 + src_loc_at)

    # -- Comparison / repr ---------------------------------------------------

    def __eq__(self, other):
        return (isinstance(other, Signature) and
                self._payload_shape == other._payload_shape and
                self._always_valid == other._always_valid and
                self._always_ready == other._always_ready and
                self._has_first_last == other._has_first_last and
                self._param_shape == other._param_shape and
                self._has_keep == other._has_keep)

    def __repr__(self):
        params = [repr(self._payload_shape)]
        if self._always_valid:
            params.append("always_valid=True")
        if self._always_ready:
            params.append("always_ready=True")
        if self._has_first_last:
            params.append("has_first_last=True")
        if self._param_shape is not None:
            params.append(f"param_shape={self._param_shape!r}")
        if self._has_keep:
            params.append("has_keep=True")
        return f"stream.Signature({', '.join(params)})"


class Interface:
    """Concrete stream interface created from a :class:`Signature`.

    This mirrors the pattern used by ``amaranth.lib.stream.Interface``:
    the constructor populates attributes from the signature members, and
    optionally replaces ``valid`` / ``ready`` with ``Const(1)`` when the
    signature specifies ``always_valid`` / ``always_ready``.

    Attributes
    ----------
    signature : :class:`Signature`
        The signature this interface was created from.
    payload : :class:`Signal`
        Payload data signal.
    valid : :class:`Signal` or :class:`Const`
        Valid handshake signal.
    ready : :class:`Signal` or :class:`Const`
        Ready handshake signal.
    p : alias for ``payload``
    """

    def __init__(self, signature, *, path=None, src_loc_at=0):
        if not isinstance(signature, Signature):
            raise TypeError(
                f"Signature of stream.Interface must be a stream.Signature, "
                f"not {signature!r}")
        self._signature = signature
        self.__dict__.update(signature.members.create(path=path, src_loc_at=1 + src_loc_at))
        if signature.always_valid:
            self.valid = Const(1)
        if signature.always_ready:
            self.ready = Const(1)

    @property
    def signature(self):
        return self._signature

    @property
    def p(self):
        """Shortcut for ``self.payload``."""
        return self.payload

    def __repr__(self):
        parts = [f"payload={self.payload!r}", f"valid={self.valid!r}", f"ready={self.ready!r}"]
        if self._signature.has_first_last:
            parts.append(f"first={self.first!r}")
            parts.append(f"last={self.last!r}")
        if self._signature.param_shape is not None:
            parts.append(f"param={self.param!r}")
        if self._signature.has_keep:
            parts.append(f"keep={self.keep!r}")
        return f"stream.Interface({', '.join(parts)})"


def core_to_extended(core_sig):
    """Convert an ``amaranth.lib.stream.Signature`` to an ``amaranth_stream.Signature``.

    Parameters
    ----------
    core_sig : :class:`amaranth.lib.stream.Signature`
        The core Amaranth stream signature to convert.

    Returns
    -------
    :class:`Signature`
        An extended stream signature with the same payload shape and
        ``always_valid`` / ``always_ready`` flags.
    """
    from amaranth.lib.stream import Signature as CoreSignature
    if not isinstance(core_sig, CoreSignature):
        raise TypeError(
            f"Expected amaranth.lib.stream.Signature, got {type(core_sig).__name__}")
    return Signature(
        core_sig._payload_shape,
        always_valid=core_sig.always_valid,
        always_ready=core_sig.always_ready,
    )


def connect_streams(m, src, dst, *, exclude=None):
    """Connect two stream interfaces combinationally.

    Wires ``src`` (source / initiator) to ``dst`` (destination / target),
    connecting handshake signals, payload, and any optional members that
    both interfaces share.

    Parameters
    ----------
    m : :class:`~amaranth.hdl.Module`
        The module to add combinational statements to.
    src : stream interface
        Source stream (drives ``payload``, ``valid``, and forward sideband
        signals).
    dst : stream interface
        Destination stream (drives ``ready``).
    exclude : set of str or None
        Optional set of member names to skip when connecting.  For example,
        ``exclude={"param"}`` will leave the ``param`` member unconnected.

    Notes
    -----
    Only members present on **both** ``src`` and ``dst`` are connected.
    If one side has ``first``/``last`` but the other does not, those signals
    are silently skipped.  The ``exclude`` parameter can be used to
    suppress connection of any member by name.
    """
    if exclude is None:
        exclude = set()

    # Determine which members exist on each side by inspecting the
    # underlying Signature.  We accept both Interface objects (which
    # have a .signature attribute) and FlippedInterface / plain objects
    # that expose the same attribute names.
    def _sig(intf):
        sig = getattr(intf, "signature", None)
        if sig is None:
            return None
        # Unwrap FlippedSignature if needed
        from amaranth.lib.wiring import FlippedSignature
        if isinstance(sig, FlippedSignature):
            return sig.flip()
        return sig

    src_sig = _sig(src)
    dst_sig = _sig(dst)

    # --- Handshake (always connected) ---
    if "valid" not in exclude:
        m.d.comb += dst.valid.eq(src.valid)
    if "ready" not in exclude:
        m.d.comb += src.ready.eq(dst.ready)

    # --- Payload ---
    if "payload" not in exclude:
        m.d.comb += dst.payload.eq(src.payload)

    # --- Optional forward members ---
    optional_members = ("first", "last", "param", "keep")
    for name in optional_members:
        if name in exclude:
            continue
        src_has = hasattr(src, name) and (src_sig is None or name in src_sig.members)
        dst_has = hasattr(dst, name) and (dst_sig is None or name in dst_sig.members)
        if src_has and dst_has:
            m.d.comb += getattr(dst, name).eq(getattr(src, name))
