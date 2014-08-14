from django.test import TestCase

from rules.continuations import *

# This will make the variables act as they would if they were fresh.
store = store.copy()
store.clear()


class Binder(object):
    throw = False

    @classmethod
    def bind(cls, context):
        x = cls()
        for k in context:
            setattr(x, k, context[k])
        return x

    def unbind(self):
        if self.throw:
            raise ValueError


class Blinder(object):
    def __call__(self):
        pass

    def bind(self, context):
        if 'throw' in context:
            raise ValueError
        return self


class Unbinder(object):
    count = 0

    def unbind(self):
        Unbinder.count += 1

    def __call__(self):
        pass


class TestContinuationStore(TestCase):
    def tearDown(self):
        store.clear()

    def test_noop(self):
        self.assertEqual(len(store), 0)
        n1 = store['noop']
        n2 = store[None]
        self.assertIs(n1, n2)
        n2 = store[False]
        self.assertIs(n1, n2)
        n2 = store['']
        self.assertIs(n1, n2)
        self.assertEqual(len(store), 4)
        self.assertIs(n1(None, None, None), None)

    def test_callable(self):
        x = lambda *a: a
        self.assertEqual(len(store), 0)
        y = store[x]
        self.assertIs(x, y)
        self.assertEqual(len(store), 0)

    def test_missing(self):
        with self.assertRaises(NoContinuationError):
            store['hello']

    def test_register(self):
        store.register(Binder)
        self.assertEqual(len(store), 1)
        self.assertIs(store['Binder'], Binder)
        store.register(Binder, name='binder')
        self.assertEqual(len(store), 2)
        self.assertIs(store['binder'], Binder)
        self.assertRaises(ValueError, store.register, Binder, name='binder')
        self.assertRaises(ValueError, store.register, Binder, name='noop')
        self.assertRaises(ValueError, store.register, Binder, name='')
        self.assertRaises(TypeError, store.register, Binder, '')

    def test_register_as_decorator(self):
        @store.register
        def x(): pass
        self.assertEqual(set(store), {'x'})
        @store.register(name='q')
        def y(): pass
        self.assertEqual(set(store), {'x', 'q'})
        with self.assertRaises(ValueError):
            @store.register(name='q')
            def z(): pass
        with self.assertRaises(TypeError):
            @store.register('w')
            def w(): pass

    def test_bind(self):
        store.register(Binder)
        x = store.bind({'hello': 5})
        self.assertNotEqual(store, x)
        self.assertEqual(set(store), set(x))
        self.assertTrue(isinstance(x['Binder'], store['Binder']))
        self.assertEqual(x['Binder'].hello, 5)

    def test_bind_no_binder(self):
        store.register(lambda: None, name='q')
        x = store.bind(None)
        self.assertIsNot(x, store)
        self.assertEqual(x, store)

    def test_bind_raises(self):
        store.register(Blinder(), name='b')
        x = store.bind(())
        self.assertEqual(x, store)
        self.assertEqual(x.bind(()), store)
        self.assertRaises(ValueError, store.bind, {'throw'})
        # For code coverage...
        x.unbind()

    def test_unbind(self):
        store.register(Binder)
        store.register(Unbinder(), name='r')
        self.assertRaises(TypeError, store.unbind)
        x = store.bind({'throw': True})
        self.assertRaises(ValueError, x.unbind)
        x = store.bind({})
        y = Unbinder.count
        x.unbind()
        self.assertEqual(Unbinder.count, y + 1)
        x.unbind()
        self.assertEqual(Unbinder.count, y + 2)
