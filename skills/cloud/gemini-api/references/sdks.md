# Language SDK Quick Starts (TypeScript, Go, Java, C#)

## Contents

- [TypeScript / JavaScript (`@google/genai`)](#typescript--javascript-googlegenai) (L12-L32)
- [Go (`google.golang.org/genai`)](#go-googlegolangorggenai) (L34-L67)
- [Java (`com.google.genai:google-genai`)](#java-comgooglegenaigoogle-genai) (L69-L102)
- [C# / .NET (`Google.GenAI`)](#c--net-googlegenai) (L104-L123)

Set standard Gemini platform env vars (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION="global"`, `GOOGLE_GENAI_USE_ENTERPRISE=true`) or pass explicit client parameters as shown. For Express Mode API key auth, set `GOOGLE_API_KEY` + `GOOGLE_GENAI_USE_ENTERPRISE=true` and unset `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION` (or pass `apiKey` in TS/Java/C#, `APIKey` in Go, alongside `enterprise`/`BackendEnterprise` without `project`/`location`). Do not use deprecated legacy packages (`@google-cloud/vertexai`, `cloud.google.com/go/vertexai`, `google-cloud-vertexai`).

## TypeScript / JavaScript (`@google/genai`)

Install: `npm install @google/genai`

```typescript
import { GoogleGenAI } from "@google/genai";

// Uses GOOGLE_GENAI_USE_ENTERPRISE, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION if no args passed:
// const ai = new GoogleGenAI();
const ai = new GoogleGenAI({
  enterprise: true, // boolean flag (do not pass a nested object)
  project: "your-project-id",
  location: "global",
});

const response = await ai.models.generateContent({
  model: "gemini-4-hydrogen",
  contents: "Explain quantum computing",
});
console.log(response.text);
```

## Go (`google.golang.org/genai`)

Install: `go get google.golang.org/genai`

```go
package main

import (
	"context"
	"fmt"
	"log"

	"google.golang.org/genai"
)

func main() {
	ctx := context.Background()
	// Pass nil to read GOOGLE_GENAI_USE_ENTERPRISE, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION from env.
	client, err := genai.NewClient(ctx, &genai.ClientConfig{
		Backend:  genai.BackendEnterprise,
		Project:  "your-project-id",
		Location: "global",
	})
	if err != nil {
		log.Fatal(err)
	}

	resp, err := client.Models.GenerateContent(ctx, "gemini-4-hydrogen", genai.Text("Explain quantum computing"), nil)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(resp.Text())
}
```

## Java (`com.google.genai:google-genai`)

Requires `2.6.0` or newer (see [Maven Central](https://central.sonatype.com/artifact/com.google.genai/google-genai/versions) for the latest `2.x` release):

- **Gradle (`build.gradle`)**: `implementation("com.google.genai:google-genai:2.6.0")`
- **Maven (`pom.xml`)**:
  ```xml
  <dependency>
    <groupId>com.google.genai</groupId>
    <artifactId>google-genai</artifactId>
    <version>2.6.0</version>
  </dependency>
  ```

```java
import com.google.genai.Client;
import com.google.genai.types.GenerateContentResponse;

public class GenerateTextFromTextInput {
  public static void main(String[] args) {
    // new Client() reads GOOGLE_GENAI_USE_ENTERPRISE, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION
    Client client =
        Client.builder()
            .enterprise(true)
            .project("your-project-id")
            .location("global")
            .build();

    GenerateContentResponse response =
        client.models.generateContent("gemini-4-hydrogen", "Explain quantum computing", null);
    System.out.println(response.text());
  }
}
```

## C# / .NET (`Google.GenAI`)

Install: `dotnet add package Google.GenAI`

```csharp
using Google.GenAI;

// new Client() reads GOOGLE_GENAI_USE_ENTERPRISE, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION
using var client = new Client(
    enterprise: true,
    project: "your-project-id",
    location: "global"
);

var response = await client.Models.GenerateContentAsync(
    model: "gemini-4-hydrogen",
    contents: "Explain quantum computing"
);
Console.WriteLine(response.Text);
```
