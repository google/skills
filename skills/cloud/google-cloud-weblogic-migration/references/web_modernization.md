# Web Tier Modernization Reference Guide

This guide explains how to migrate legacy server-rendered presentation
components (JSPs, servlets, and web MVC actions) to modern decoupled Single Page
Applications (SPAs) backed by RESTful APIs.

## Table of Contents

*   [1. JSP to React/Angular Migration Strategy](#1-jsp-to-react-angular-migration-strategy) (Line 15)
*   [2. Migrating Servlets to REST Endpoints](#2-migrating-servlets-to-rest-endpoints) (Line 115)
*   [3. Session State Decoupling](#3-session-state-decoupling) (Line 165)

--------------------------------------------------------------------------------

## 1. JSP to React/Angular Migration Strategy

Legacy Java web applications compile JSP pages dynamically into servlets. The
modernization flow requires separating the HTML structure from the Java-based
data flow.

### Before: Legacy Struts/JSP Page (`editProfile.jsp`)

```html
<%@ taglib uri="/WEB-INF/struts-html.tld" prefix="html" %>
<%@ taglib uri="/WEB-INF/struts-bean.tld" prefix="bean" %>

<html:form action="/saveProfile.do" method="POST">
    <div class="form-group">
        <label>Email Address:</label>
        <html:text property="email" size="30" />
    </div>
    <div class="form-group">
        <label>Phone Number:</label>
        <html:text property="phone" size="15" />
    </div>
    <html:submit value="Update Profile" />
</html:form>
```

### After: Decoupled REST + React SPA

#### A. Spring Boot REST Controller (`ProfileController.java`)

```java
package com.acme.medimed.web;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/profile")
@CrossOrigin(origins = "*") // Configure CORS for SPA access
public class ProfileController {

    private final PatientService patientService;

    public ProfileController(PatientService patientService) {
        this.patientService = patientService;
    }

    @PostMapping("/save")
    public ResponseEntity<Void> saveProfile(@RequestBody ProfileRequest request) {
        patientService.updatePatientProfile(request.getEmail(), request.getPhone());
        return ResponseEntity.ok().build();
    }
}
```

#### B. React Frontend Component (`EditProfile.jsx`)

```jsx
import React, { useState } from 'react';

export default function EditProfile() {
    const [profile, setProfile] = useState({ email: '', phone: '' });

    const handleSubmit = async (e) => {
        e.preventDefault();
        const response = await fetch('/api/profile/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(profile)
        });
        if (response.ok) {
            alert('Profile updated successfully!');
        }
    };

    return (
        <form onSubmit={handleSubmit}>
            <div className="form-group">
                <label>Email Address:</label>
                <input
                    type="email"
                    value={profile.email}
                    onChange={e => setProfile({...profile, email: e.target.value})}
                />
            </div>
            <div className="form-group">
                <label>Phone Number:</label>
                <input
                    type="text"
                    value={profile.phone}
                    onChange={e => setProfile({...profile, phone: e.target.value})}
                />
            </div>
            <button type="submit">Update Profile</button>
        </form>
    );
}
```

--------------------------------------------------------------------------------

## 2. Migrating Servlets to REST Endpoints

Legacy servlets directly write HTML output streams or handle request
dispatching.

### Before: Custom HttpServlet (`AdminReportServlet.java`)

```java
public class AdminReportServlet extends HttpServlet {
    protected void doGet(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {
        response.setContentType("application/json");
        PrintWriter out = response.getWriter();
        out.print("{\"status\":\"active\", \"total_users\": 104}");
        out.flush();
    }
}
```

### After: Quarkus JAX-RS Endpoint (`AdminReportResource.java`)

```java
package com.acme.medimed.web;

import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;

@Path("/api/admin/report")
@Produces(MediaType.APPLICATION_JSON)
public class AdminReportResource {

    @GET
    public AdminReport getReport() {
        return new AdminReport("active", 104);
    }

    public static class AdminReport {
        public String status;
        public int totalUsers;

        public AdminReport(String status, int totalUsers) {
            this.status = status;
            this.totalUsers = totalUsers;
        }
    }
}
```

--------------------------------------------------------------------------------

## 3. Session State Decoupling

Legacy Java web applications store state in the server-side `HttpSession`. In
Cloud Run or serverless containers, instances scale to zero and shift
dynamically, which breaks session persistence.

### Before: Server-bound Session Writes

```java
HttpSession session = request.getSession();
session.setAttribute("user_key", userObject);
```

### After: Token-based Stateless JWT

Expose auth headers in responses and verify claims at the API Gateway or
framework level:

```java
// Spring Security Config utilizing JWT verification filters:
http.sessionManagement()
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS);
```

If state must persist, use a **Redis Cache** shared across your Cloud Run
instances:

*   Add the `spring-session-data-redis` library.
*   Annotate configuration with `@EnableRedisHttpSession`.
