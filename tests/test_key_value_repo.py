"""Exercise the repository rule's Python-compatible body with a fake Bazel context.

This does not replace execution by Starlark/Bazel. Generated literal-only code is
parsed, never executed; native Bazel integration remains a separate gate.
"""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(os.environ.get('MGK_RULES_ROOT', Path(__file__).resolve().parents[1]))
KEYS = ['DEFCONFIG_OVERLAYS', 'KERNEL_VERSION', 'SOURCE_DATE_EPOCH']


def generate(environment=None, additional=None):
    namespace = {'repository_rule': lambda **kwargs: kwargs,
                 'attr': SimpleNamespace(string_dict=lambda: None)}
    source = (ROOT / 'kleaf/key_value_repo.bzl').read_text()
    exec(compile(source, 'key_value_repo.bzl', 'exec'), namespace)
    files = {}
    context = SimpleNamespace(os=SimpleNamespace(environ=environment or {}),
                              attr=SimpleNamespace(additional_values=additional or {}),
                              file=lambda name, data, executable: files.update({name: (data, executable)}))
    namespace['_impl'](context)
    values = {}
    for node in ast.parse(files['dict.bzl'][0]).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            raise AssertionError('Generated output is not a sequence of constant assignments')
        value = ast.literal_eval(node.value)
        if not isinstance(value, str):
            raise AssertionError('Generated value is not a string')
        values[node.targets[0].id] = value
    return values, files, namespace['key_value_repo']


class KeyValueRepoTests(unittest.TestCase):
    def test_missing_values_remain_empty(self):
        self.assertEqual(generate()[0], dict.fromkeys(KEYS, ''))

    def test_current_kernel_values(self):
        data = dict(zip(KEYS, ['malachite.config', 'kernel-6.1', '1788641561']))
        self.assertEqual(generate(data)[0], data)

    def test_environment_is_trimmed_as_before(self):
        self.assertEqual(generate({'KERNEL_VERSION': '  kernel-6.1\n'})[0]['KERNEL_VERSION'], 'kernel-6.1')

    def test_environment_string_roundtrips(self):
        for value in ['quote"value', "quote'value", 'back\\slash', 'a\nb', 'a\tb', 'a\x00b']:
            with self.subTest(value=value):
                self.assertEqual(generate({'DEFCONFIG_OVERLAYS': value})[0]['DEFCONFIG_OVERLAYS'], value)

    def test_additional_strings_are_not_trimmed(self):
        for value in ['  value  ', '"\\\n\t', 'a\x00b']:
            self.assertEqual(generate(additional={'EXTRA': value})[0]['EXTRA'], value)

    def test_no_extra_generated_assignment(self):
        value = '"\nUNEXPECTED = "changed"\n#'
        values, _, _ = generate({'DEFCONFIG_OVERLAYS': value})
        self.assertEqual(set(values), set(KEYS))
        self.assertEqual(values['DEFCONFIG_OVERLAYS'], value)

    def test_rule_and_output_contract(self):
        _, files, rule = generate()
        self.assertEqual(rule['environ'], KEYS)
        self.assertTrue(rule['local'])
        self.assertEqual(set(files), {'BUILD', 'dict.bzl'})
        self.assertTrue(all(not executable for _, executable in files.values()))
        self.assertIn('srcs = ["dict.bzl"]', files['BUILD'][0])


if __name__ == '__main__':
    unittest.main()
