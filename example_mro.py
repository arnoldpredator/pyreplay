class Serializer:
    """Base: export() calls payload(), which subclasses override."""

    def export(self):
        return "<" + self.payload() + ">"

    def payload(self):
        return "data"


class JsonMixin:
    def payload(self):
        return '{"body": ' + super().payload() + "}"


class ZipMixin:
    def payload(self):
        return "zip(" + super().payload() + ")"


class Exporter(ZipMixin, JsonMixin, Serializer):
    """The C3 chain: Exporter -> ZipMixin -> JsonMixin -> Serializer."""


e = Exporter()
print(e.export())
