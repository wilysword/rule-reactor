from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rules.deferred import *


class TestDeferred(TestCase):
    def test_init(self):
        self.assertRaises(TypeError, DeferredValue)

    def test_slots(self):
        self.assertEqual(DeferredValue.__slots__, ())

    def test_issubclass(self):
        self.assertTrue(issubclass(DeferredDict, DeferredValue))
        self.assertTrue(issubclass(DeferredList, DeferredValue))
        self.assertTrue(issubclass(Selector, DeferredValue))
        self.assertTrue(issubclass(Function, DeferredValue))

    def test_isinstance(self):
        self.assertTrue(isinstance(DeferredDict(), DeferredValue))
        self.assertTrue(isinstance(DeferredList(), DeferredValue))
        self.assertTrue(isinstance(Selector(('const', 0), ()), DeferredValue))
        self.assertTrue(isinstance(Function('min', (0, 1)), DeferredValue))


class TestSelector(TestCase):
    def test_init(self):
        self.assertRaises(TypeError, Selector, (1, 2, 3), ())
        self.assertRaises(TypeError, Selector, (1, 2, 3))
        self.assertRaises(NotImplementedError, Selector, 'hello', ())
        # We don't try to coerce numbers or numeric strings.
        self.assertRaises(NotImplementedError, Selector, '1', ())
        self.assertRaises(NotImplementedError, Selector, 1., ())

    def test_slots(self):
        self.assertEqual(Selector.__slots__, ('stype', 'chain', 'first'))
        s = Selector('const', ())
        with self.assertRaises(AttributeError):
            s.random = 'me'

    def test_init_model(self):
        ct = ContentType.objects.all()[0]
        model = ct.app_label + '.' + ct.model
        s = Selector(('model', model), ())
        self.assertEqual(s.stype, ('model', model))
        self.assertIs(s.first(None), ct.model_class())
        self.assertRaises(ValueError, Selector, ('model', 'random.model.malformatted'), ())
        self.assertRaises(ValueError, Selector, ('model', 'random.model'), ())
        self.assertRaises(ValueError, Selector, 'model', ())

    def test_maybe_const_model(self):
        ct = ContentType.objects.all()[0]
        model = ct.app_label + '.' + ct.model
        s = Selector(('model', model), ())
        self.assertIs(s.maybe_const(), ct.model_class())
        s1 = Selector(('model', model), ('objects',))
        self.assertIs(s1.maybe_const(), s1)

    def test_init_const(self):
        s = Selector('const', ())
        self.assertEqual(s.stype, ('const', None))
        self.assertIs(s.first(None), None)
        s = Selector(('const', 1), ())
        self.assertEqual(s.stype, ('const', 1))
        self.assertEqual(s.first(None), 1)
        self.assertRaises(ValueError, Selector, 'const', (1,))

    def test_maybe_const_const(self):
        s = Selector('const', ())
        self.assertIs(s.maybe_const(), None)
        s = Selector(('const', 1), ())
        self.assertEqual(s.maybe_const(), 1)

    def test_init_extra(self):
        s = Selector('extra', ())
        self.assertEqual(s.stype, 'extra')
        self.assertRaises(TypeError, s.first, None)
        self.assertRaises(KeyError, s.first, {})
        self.assertEqual(s.first({'extra': 1}), 1)
        self.assertIs(s.maybe_const(), s)

    def test_init_int(self):
        s = Selector(0, ())
        self.assertEqual(s.stype, 0)
        self.assertRaises(TypeError, s.first, None)
        self.assertRaises(KeyError, s.first, {})
        self.assertRaises(IndexError, s.first, {'objects': ()})
        self.assertEqual(s.first({'objects': [5]}), 5)
        self.assertIs(s.maybe_const(), s)

    def test_init_deferred(self):
        s0 = Selector(0, ())
        s = Selector(s0, ())
        self.assertIs(s.stype, s0)
        self.assertRaises(TypeError, s.first, None)
        self.assertRaises(KeyError, s.first, {})
        self.assertRaises(IndexError, s.first, {'objects': ()})
        self.assertEqual(s.first({'objects': [5]}), 5)
        s1 = Selector('const', ())
        s = Selector(s1, ())
        self.assertIs(s.first({}), None)

    def test_maybe_const_deferred(self):
        s0 = Selector(0, ())
        s = Selector(s0, ())
        self.assertIs(s.maybe_const(), s0)
        s = Selector(s0, ('x',))
        self.assertIs(s.maybe_const(), s)
        s1 = Selector(('const', 5), ())
        s = Selector(s1, ())
        self.assertEqual(s.maybe_const(), 5)
        s = Selector(s1, ('x',))
        self.assertIs(s.maybe_const(), s)

    def test_init_chain(self):
        s1 = Selector('const', None)
        s2 = Selector(0, ('x',))
        s = Selector(0, DeferredList([s1]))
        self.assertEqual(s.chain, [None])
        s = Selector(0, DeferredList([s2]))
        self.assertEqual(s.chain, DeferredList([s2]))

    def test_eq(self):
        s1 = Selector(1, ['x'])
        s2 = Selector(1, ['x'])
        s3 = Selector(1, ['y'])
        s4 = Selector(2, ['x'])
        self.assertEqual(s1, s1)
        self.assertEqual(s1, s2)
        self.assertNotEqual(s1, s3)
        self.assertNotEqual(s1, s4)
        f = Function('sum', ())
        self.assertNotEqual(s1, f)
        self.assertEqual(hash(s1), hash(s1))
        self.assertEqual(hash(s1), hash(s2))
        self.assertNotEqual(hash(s1), hash(s3))
        self.assertNotEqual(hash(s1), hash(s4))

    def test_get_value(self):
        s = Selector(('const', 5), None)
        i = {}
        self.assertEqual(s.get_value(i), 5)
        self.assertEqual(i[id(s)], 5)
        i[id(s)] = 4
        self.assertEqual(s.get_value(i), 4)
        s = Selector(0, None)
        # The chain must be iterable, so if it's None, we replace it with an empty tuple
        self.assertEqual(s.chain, ())

    def test_get_value_from_dict(self):
        s = Selector('extra', ('one',))
        self.assertEqual(s.get_value({'extra': {'one': 1}}), 1)
        self.assertRaises(ChainError, s.get_value, {'extra': None})
        self.assertRaises(ChainError, s.get_value, {'extra': {}})

    def test_get_value_from_list(self):
        s = Selector('extra', (0,))
        self.assertEqual(s.get_value({'extra': [1]}), 1)
        self.assertRaises(ChainError, s.get_value, {'extra': None})
        self.assertRaises(ChainError, s.get_value, {'extra': []})

    def test_get_value_callable_simple(self):
        s = Selector(0, [('__str__', 42)])
        self.assertEqual(s.get_value({'objects': [int]}), '42')
        # Function will raise a TypeError, gets converted to ChainError.
        self.assertRaises(ChainError, s.get_value, {'objects': [str]})

    def test_get_value_callable_args(self):
        s = Selector(('model', 'contenttypes.contenttype'),
                     ('objects', ('values', ['app_label', 'model'])))
        x = s.get_value({})
        self.assertTrue(x)
        self.assertTrue(isinstance(x[0], dict))
        self.assertIn('app_label', x[0])
        self.assertIn('model', x[0])

    def test_get_value_callable_deferred_args(self):
        args = DeferredList(['app_label', Selector(0, ())])
        s = Selector(('model', 'contenttypes.contenttype'),
                     ('objects', ('values', args)))
        self.assertRaises(ChainError, s.get_value, {})
        x = s.get_value({'objects': ['model']})
        self.assertTrue(x)
        self.assertTrue(isinstance(x[0], dict))
        self.assertIn('app_label', x[0])
        self.assertIn('model', x[0])
        self.assertNotIn('name', x[0])
        # Changing the input now changes the output
        x = s.get_value({'objects': ['name']})
        self.assertTrue(x)
        self.assertTrue(isinstance(x[0], dict))
        self.assertIn('app_label', x[0])
        self.assertNotIn('model', x[0])
        self.assertIn('name', x[0])

    def test_get_value_callable_kwargs(self):
        s = Selector(('model', 'contenttypes.contenttype'),
                     ('objects', ('filter', {'app_label': 'contenttypes'})))
        x = s.get_value({})
        self.assertEqual(len(x), 1)
        self.assertTrue(isinstance(x[0], ContentType))
        self.assertEqual(x[0].app_label, 'contenttypes')

    def test_get_value_callable_deferred_args(self):
        kwargs = DeferredDict({'app_label': Selector(0, None)})
        s = Selector(('model', 'contenttypes.contenttype'),
                     ('objects', ('filter', kwargs)))
        self.assertRaises(ChainError, s.get_value, {})
        x = s.get_value({'objects': ['contenttypes']})
        self.assertEqual(len(x), 1)
        self.assertTrue(isinstance(x[0], ContentType))
        self.assertEqual(x[0].app_label, 'contenttypes')
        x = s.get_value({'objects': ['random']})
        self.assertEqual(len(x), 0)


class TestFunction(TestCase):
    def test_init(self):
        f = Function('sum', [(1, 2, 3)])
        self.assertIs(f.func, sum)
        self.assertEqual(f.name, 'sum')
        self.assertEqual(f.args, [(1, 2, 3)])
        self.assertRaises(ValueError, Function, 'random', ())
        f = Function('sum', DeferredList([(1, 2, 3)]))
        # because maybe_const is called
        self.assertEqual(f.args, [(1, 2, 3)])

    def test_slots(self):
        self.assertEqual(Function.__slots__, ('func', 'name', 'args'))
        f = Function('sum', [(1, 2, 3)])
        with self.assertRaises(AttributeError):
            f.random = 'me'

    def test_get_value(self):
        i = {}
        f = Function('sum', [(1, 2, 3)])
        x = f.get_value(i)
        self.assertEqual(x, 6)
        self.assertIn(id(f), i)
        self.assertEqual(i[id(f)], x)
        i[id(f)] = 8
        self.assertEqual(f.get_value(i), 8)
        self.assertEqual(f._get_value(i), 6)

    def test_maybe_const(self):
        f = Function('sum', [(1, 2, 3)])
        self.assertEqual(f.maybe_const(), 6)
        s = Selector(0, ())
        f = Function('sum', DeferredList([DeferredList([s, 2, 3])]))
        self.assertIs(f.maybe_const(), f)

    def test_get_value_with_selector(self):
        i = {'objects': (1,)}
        s = Selector(0, ())
        f = Function('sum', DeferredList([DeferredList([s, 2, 3])]))
        self.assertEqual(f.get_value(i), 6)
        i['objects'] = (2,)
        self.assertEqual(f.get_value(i), 6)
        i = {'objects': (2,)}
        self.assertEqual(f.get_value(i), 7)

    def test_eq(self):
        f1 = Function('sum', [(1, 2, 3)])
        f2 = Function('sum', [(1, 2, 3)])
        f3 = Function('set', [(1, 2, 3)])
        f4 = Function('sum', [(1, 3)])
        self.assertEqual(f1, f1)
        self.assertEqual(f1, f2)
        self.assertNotEqual(f1, f3)
        self.assertNotEqual(f1, f4)
        s = Selector(0, ())
        self.assertNotEqual(f1, s)
        self.assertEqual(hash(f1), hash(f1))
        self.assertEqual(hash(f1), hash(f2))
        self.assertNotEqual(hash(f1), hash(f3))
        self.assertNotEqual(hash(f1), hash(f4))


class TestDeferredDict(TestCase):
    def test_slots(self):
        self.assertEqual(DeferredDict.__slots__, ())
        d = DeferredDict()
        with self.assertRaises(AttributeError):
            d.random = 'me'

    def test_maybe_const(self):
        d = DeferredDict()
        self.assertIsNot(d.maybe_const(), d)
        self.assertEqual(d.maybe_const(), {})
        d = DeferredDict({'one': 1})
        self.assertIsNot(d.maybe_const(), d)
        self.assertEqual(d.maybe_const(), {'one': 1})
        d = DeferredDict({'one': Function('max', (2, 4))})
        self.assertIsNot(d.maybe_const(), d)
        self.assertEqual(d.maybe_const(), {'one': 4})
        d = DeferredDict({'one': Selector(0, None)})
        self.assertIs(d.maybe_const(), d)

    def test_get_value(self):
        d = DeferredDict({'one': Selector(0, None), 'two': 2})
        self.assertEqual(d.get_value({'objects': [1]}), {'one': 1, 'two': 2})
        self.assertEqual(d.get_value({'objects': ['one']}), {'one': 'one', 'two': 2})

    def test_keys_ignored(self):
        s = Selector(0, None)
        d = DeferredDict({s: 1})
        self.assertIsNot(d.maybe_const(), d)
        self.assertEqual(d.maybe_const(), {s: 1})
        self.assertEqual(d.get_value({}), {s: 1})


class TestDeferredList(TestCase):
    def test_slots(self):
        self.assertEqual(DeferredList.__slots__, ())
        l = DeferredList()
        with self.assertRaises(AttributeError):
            l.random = 'me'

    def test_maybe_const(self):
        l = DeferredList()
        self.assertIsNot(l.maybe_const(), l)
        self.assertEqual(l.maybe_const(), [])
        l = DeferredList(['one', 1])
        self.assertIsNot(l.maybe_const(), l)
        self.assertEqual(l.maybe_const(), ['one', 1])
        l = DeferredList(['one', Function('max', (2, 4))])
        self.assertIsNot(l.maybe_const(), l)
        self.assertEqual(l.maybe_const(), ['one', 4])
        l = DeferredList(['one', Selector(0, None)])
        self.assertIs(l.maybe_const(), l)

    def test_get_value(self):
        l = DeferredList(['one', Selector(0, None), 2])
        self.assertEqual(l.get_value({'objects': [1]}), ['one', 1, 2])
        self.assertEqual(l.get_value({'objects': ['one']}), ['one', 'one', 2])
