# Schemantic

Schemantic is a general-purpose Dart library used for defining strongly typed
data classes that automatically bind to reusable runtime JSON schemas. It is
standard for the `genkit-dart` framework but works independently as well.

- [Core Concepts](#core-concepts): Lines 18-27
- [Installation](#installation): Lines 29-49
- [Basic Usage](#basic-usage): Lines 51-107
- [Primitive Schemas](#primitive-schemas): Lines 109-122
- [Union Types (AnyOf)](#union-types-anyof): Lines 124-142
- [Field Annotations](#field-annotations): Lines 144-165
- [Recursive Schemas](#recursive-schemas): Lines 167-180
- [Non-nullable getters throw on partial data](#non-nullable-getters-throw-on-partial-data): Lines 182-190

---

## Core Concepts

Always use `schemantic` when strongly typed JSON parsing or programmatic schema
validation is required.

- Annotate your abstract classes with `@Schema()`.
- Use the `$` prefix for abstract schema class names (e.g.,
  `abstract class $User`).
- Always run `dart run build_runner build` to generate the `.g.dart` schema
  files.

## Installation

Add dependencies. The code generator lives in a **separate**
`schemantic_builder` package, so you must add it as a dev dependency too:

```bash
dart pub add schemantic
dart pub add dev:schemantic_builder
dart pub add dev:build_runner
```

> **Gotcha:** if `schemantic_builder` is missing, `dart run build_runner build`
> completes "successfully" but reports `wrote 0 outputs` and generates no
> `.g.dart` files, with no error explaining why. If you see zero outputs,
> confirm
> `schemantic_builder` is in your `dev_dependencies`.

> **Note:** plain `dart run build_runner build` is correct. Recent
> `build_runner`
> versions removed `--delete-conflicting-outputs` (it is now ignored and warns
> "These options have been removed and were ignored"), so do not pass it.

## Basic Usage

1. **Defining a schema:**

```dart
import 'package:schemantic/schemantic.dart';

part 'my_file.g.dart'; // Must match the filename

@Schema()
abstract class $MyObj {
  String get name;
  $MySubObj get subObj;
}

@Schema()
abstract class $MySubObj {
  String get foo;
}
```

2. **Using the Generated Class:**

The builder creates a concrete class `MyObj` (no `$`) with a factory constructor
(`MyObj.fromJson`) and a regular constructor.

```dart
// Creating an instance
final obj = MyObj(name: 'test', subObj: MySubObj(foo: 'bar'));

// Serializing to JSON
print(obj.toJson()); 

// Parsing from JSON
final parsed = MyObj.fromJson({'name': 'test', 'subObj': {'foo': 'bar'}});
```

3. **Accessing Schemas at Runtime:**

The generated data classes have a static `$schema` field (of type
`SchemanticType<T>`) which can be used to pass the definition into functions or
to extract the raw JSON schema.

```dart
// The JSON Schema, as a plain map
final Map<String, Object?> jsonSchema = MyObj.$schema.jsonSchema();
print(jsonEncode(jsonSchema)); // import 'dart:convert';

// Validate arbitrary JSON at runtime (empty list = valid)
final errors = await MyObj.$schema.validate({'invalid': 'data'});
for (final e in errors) {
  print(e);
}

// Parse JSON into the typed class
final MyObj obj = MyObj.$schema.parse({'name': 'x', 'subObj': {'foo': 'y'}});
```

## Primitive Schemas

When a full data class is not required, Schemantic provides functions to create
schemas dynamically.

```dart
final ageSchema = SchemanticType.integer(description: 'Age in years', minimum: 0);
final nameSchema = SchemanticType.string(minLength: 2);
final nothingSchema = SchemanticType.voidSchema();
final anySchema = SchemanticType.dynamicSchema();

final userSchema = SchemanticType.map(.string(), .integer()); // Map<String, int>
final tagsSchema = SchemanticType.list(.string()); // List<String>
```

## Union Types (AnyOf)

To allow a field to accept multiple types, use `@AnyOf`.

```dart
@Schema()
abstract class $Poly {
  @AnyOf([int, String, $MyObj])
  Object? get id;
}
```

Schemantic generates a specific helper class (e.g., `PolyId`) to handle the
values:

```dart
final poly1 = Poly(id: PolyId.int(123));
final poly2 = Poly(id: PolyId.string('abc'));
```

## Field Annotations

You can use specialized annotations for more validation boundaries:

```dart
@Schema()
abstract class $User {
  @IntegerField(
    name: 'years_old', // Change JSON key
    description: 'Age of the user',
    minimum: 0,
    defaultValue: 18,
  )
  int? get age;

  @StringField(
    minLength: 2,
    enumValues: ['user', 'admin'], 
  )
  String get role;
}
```

## Recursive Schemas

For recursive structures (like trees), must use `useRefs: true` inside the
generated jsonSchema property. You define it normally:

```dart
@Schema()
abstract class $Node {
  String get id;
  List<$Node>? get children;
}
```
*Note*: `Node.$schema.jsonSchema(useRefs: true)` generates schemas with JSON
Schema `$ref`.

## Non-nullable getters throw on partial data

Generated getters for required fields are non-nullable casts (e.g.
`_json['estimatedCostUsd'] as num`). A JSON blob that is missing such a field
throws on access (`Null is not a subtype of num`) rather than returning a
default — this commonly bites computed/optional values that were never written,
e.g. when reloading a partially populated state blob. Make computed or optional
fields nullable (`num?`) or give them a `defaultValue` so partial data can still
be read.
