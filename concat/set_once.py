class SetOnce[T]:
    def __set_name__(self, owner, name: str) -> None:
        self._name = name
        self._storage_name = f'_SetOnce_{self._name}'

    def __get__(self, instance, owner=None) -> T:
        return getattr(instance, self._storage_name)

    def __set__(self, instance, value: T) -> None:
        if hasattr(instance, self._storage_name):
            raise AttributeError(
                f'Attribute "{self._name}" cannot be set more than once'
            )
        return setattr(instance, self._storage_name, value)
