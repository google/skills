import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.openrewrite.InMemoryExecutionContext;
import org.openrewrite.Parser;
import org.openrewrite.SourceFile;
import org.openrewrite.java.JavaParser;
import org.openrewrite.java.JavaVisitor;
import org.openrewrite.java.tree.J;
import org.openrewrite.java.tree.TypeTree;
import org.openrewrite.tree.ParseError;

/**
 * OpenRewriteAstAnalyzer is a standalone Abstract Syntax Tree (AST) static analyzer powered by
 * OpenRewrite.
 *
 * <p>During Phase 1 (Analysis &amp; Discovery) of the WebLogic migration workflow, this analyzer
 * scans a target legacy Java EE / WebLogic repository to extract precise, quantitative AST metrics.
 * It identifies and counts occurrences of WebLogic specific APIs, Enterprise JavaBeans (EJBs), Java
 * Message Service (JMS), Java Naming and Directory Interface (JNDI), distributed transactions, data
 * access frameworks, security annotations, web tier components, advanced container features, and
 * cloud-unfriendly patterns.
 *
 * <p>The output is serialized as a structured JSON string matching the exact schema required by
 * {@code static_analyzer.py}.
 */
public class OpenRewriteAstAnalyzer {

  /**
   * Data container class holding integer counters for each category of WebLogic/Java EE artifact
   * discovered during AST traversal of the codebase.
   */
  static class Metrics {
    // --- WebLogic Specific APIs & Middleware ---
    int wlsImportsCount = 0;
    int loggingCount = 0;
    int securityCount = 0;
    int transactionCount = 0;
    int wlsTransactionManagerCount = 0;
    int wlsUserTransactionCount = 0;
    int coherenceCount = 0;
    int workmanagerCount = 0;
    int jwsApiCount = 0;

    // --- Enterprise JavaBeans (EJB) ---
    int statelessCount = 0;
    int statefulCount = 0;
    int singletonCount = 0;
    int mdbCount = 0;
    int entityBeanCount = 0;
    int ejb2xHomeInterfacesCount = 0;

    // --- Java Message Service (JMS) ---
    int jmsImportsCount = 0;
    int jmsProducerCount = 0;
    int jmsConsumerCount = 0;
    int jmsQueueCount = 0;
    int jmsTopicCount = 0;

    // --- Java Naming and Directory Interface (JNDI) ---
    int initialContextCount = 0;
    int lookupsCount = 0;

    // --- Transactions & Distributed Coordination ---
    int userTransactionCount = 0;
    int xaDatasourceCount = 0;
    int xaResourceCount = 0;
    int declarativeTransactionCount = 0;
    int standardTransactionManagerCount = 0;

    // --- Data Access & Persistence ---
    int jdbcConnectionsCount = 0;
    int jpaEntitiesCount = 0;
    int hibernateSessionsCount = 0;
    int springDataRepositoriesCount = 0;

    // --- Security & Authorization ---
    int rolesAllowedCount = 0;
    int runAsCount = 0;
    int userInRoleCount = 0;
    int userPrincipalCount = 0;

    // --- Web Tier & Presentation Layer ---
    int servletsCount = 0;
    int filtersCount = 0;
    int listenersCount = 0;
    int jaxRsEndpointsCount = 0;
    int springControllersCount = 0;
    int strutsCount = 0;
    int jsfCount = 0;
    int httpSessionsCount = 0;

    // --- Advanced Container Features & Web Services ---
    int timersCount = 0;
    int webServicesCount = 0;
    int jaxRpcCount = 0;
    int jaxWsCount = 0;
    int batchProcessingCount = 0;
    int jmxMbeansCount = 0;

    // --- Cloud-Unfriendly Patterns & Migration Blockers ---
    int rawThreadsCount = 0;
    int nativeProcessesCount = 0;
    int directSocketsCount = 0;
    int jaasLoginModulesCount = 0;
    int specificProxiesCount = 0;
    int fileIoCount = 0;
    int rmiCorbaCount = 0;
    int javaMailCount = 0;
  }

  /**
   * Main entry point for CLI execution.
   *
   * <p>Recursively walks the target directory for Java source files ({@code .java} and {@code
   * .jws}), constructs OpenRewrite AST compilation units, traverses them with {@link
   * MetricsVisitor}, and prints the compiled JSON report to standard output.
   *
   * @param args Command-line arguments; {@code args[0]} must specify the target project root
   *     directory.
   * @throws IOException If an I/O error occurs while reading source files from disk.
   */
  public static void main(String[] args) throws IOException {
    // Validate command-line argument count
    if (args.length < 1) {
      System.err.println("Usage: OpenRewriteAstAnalyzer <target_directory>");
      System.exit(1);
    }

    Path targetDir = Paths.get(args[0]);
    List<Path> javaFiles;

    // Recursively walk filesystem to locate all .java and .jws (Java Web Service) files
    try (Stream<Path> walk = Files.walk(targetDir)) {
      javaFiles =
          walk.filter(
                  p -> {
                    String s = p.toString().toLowerCase();
                    return s.endsWith(".java") || s.endsWith(".jws") || s.endsWith(".ejb");
                  })
              .collect(Collectors.toList());
    }

    // Convert file paths into OpenRewrite Parser.Input stream suppliers
    List<Parser.Input> inputs =
        javaFiles.stream()
            .map(
                p -> {
                  Path targetPath = p;
                  if (p.toString().endsWith(".ejb")) {
                    targetPath = Paths.get(p.toString() + ".java");
                  }
                  final Path finalPath = targetPath;
                  return new Parser.Input(
                      finalPath,
                      () -> {
                        try {
                          return Files.newInputStream(p);
                        } catch (IOException e) {
                          throw new RuntimeException(e);
                        }
                      });
                })
            .collect(Collectors.toList());

    // Build OpenRewrite JavaParser configured for current Java LTS syntax
    JavaParser parser = JavaParser.fromJavaVersion().build();

    // Parse source inputs into AST CompilationUnit nodes in an in-memory execution context
    List<SourceFile> sourceFiles =
        parser
            .parseInputs(inputs, targetDir, new InMemoryExecutionContext())
            .collect(Collectors.toList());

    List<J.CompilationUnit> cus =
        sourceFiles.stream()
            .filter(s -> s instanceof J.CompilationUnit)
            .map(J.CompilationUnit.class::cast)
            .collect(Collectors.toList());

    List<ParseError> parseErrors =
        sourceFiles.stream()
            .filter(s -> s instanceof ParseError)
            .map(ParseError.class::cast)
            .collect(Collectors.toList());

    if (!parseErrors.isEmpty()) {
      System.err.println("Warning: Failed to parse " + parseErrors.size() + " files:");
      for (ParseError error : parseErrors) {
        System.err.println("  " + error.getSourcePath() + " -> " + error.toString());
      }
    }

    // Initialize metrics container and visitor
    Metrics metrics = new Metrics();
    MetricsVisitor visitor = new MetricsVisitor();

    // Traverse each parsed compilation unit to populate metrics
    for (J.CompilationUnit cu : cus) {
      visitor.visit(cu, metrics);
    }

    // Serialize collected metrics to JSON and output to stdout
    System.out.println(buildJson(metrics));
  }

  /**
   * Serializes the populated {@link Metrics} data container into a formatted JSON string.
   *
   * <p>The resulting JSON matches the exact schema expected by the Python static analysis pipeline
   * ({@code static_analyzer.py}).
   *
   * @param m The populated {@link Metrics} instance.
   * @return A formatted JSON string representing the AST analysis results.
   */
  private static String buildJson(Metrics m) {
    StringBuilder sb = new StringBuilder();
    sb.append("{\n");

    // Serialize WebLogic specific API metrics
    sb.append("  \"weblogic_api\": {\n");
    sb.append("    \"imports_count\": ").append(m.wlsImportsCount).append(",\n");
    sb.append("    \"logging_count\": ").append(m.loggingCount).append(",\n");
    sb.append("    \"security_count\": ").append(m.securityCount).append(",\n");
    sb.append("    \"transaction_count\": ").append(m.transactionCount).append(",\n");
    sb.append("    \"wls_transaction_manager_count\": ")
        .append(m.wlsTransactionManagerCount)
        .append(",\n");
    sb.append("    \"wls_user_transaction_count\": ")
        .append(m.wlsUserTransactionCount)
        .append(",\n");
    sb.append("    \"coherence_count\": ").append(m.coherenceCount).append(",\n");
    sb.append("    \"workmanager_count\": ").append(m.workmanagerCount).append(",\n");
    sb.append("    \"jws_api_count\": ").append(m.jwsApiCount).append("\n");
    sb.append("  },\n");

    // Serialize EJB metrics
    sb.append("  \"ejb\": {\n");
    sb.append("    \"stateless_count\": ").append(m.statelessCount).append(",\n");
    sb.append("    \"stateful_count\": ").append(m.statefulCount).append(",\n");
    sb.append("    \"singleton_count\": ").append(m.singletonCount).append(",\n");
    sb.append("    \"mdb_count\": ").append(m.mdbCount).append(",\n");
    sb.append("    \"entity_bean_count\": ").append(m.entityBeanCount).append(",\n");
    sb.append("    \"ejb_2x_home_interfaces_count\": ")
        .append(m.ejb2xHomeInterfacesCount)
        .append("\n");
    sb.append("  },\n");

    // Serialize JMS metrics
    sb.append("  \"jms\": {\n");
    sb.append("    \"imports_count\": ").append(m.jmsImportsCount).append(",\n");
    sb.append("    \"producer_count\": ").append(m.jmsProducerCount).append(",\n");
    sb.append("    \"consumer_count\": ").append(m.jmsConsumerCount).append(",\n");
    sb.append("    \"queue_count\": ").append(m.jmsQueueCount).append(",\n");
    sb.append("    \"topic_count\": ").append(m.jmsTopicCount).append("\n");
    sb.append("  },\n");

    // Serialize JNDI metrics
    sb.append("  \"jndi\": {\n");
    sb.append("    \"initial_context_count\": ").append(m.initialContextCount).append(",\n");
    sb.append("    \"lookups_count\": ").append(m.lookupsCount).append("\n");
    sb.append("  },\n");

    // Serialize Transaction metrics
    sb.append("  \"transactions\": {\n");
    sb.append("    \"user_transaction_count\": ").append(m.userTransactionCount).append(",\n");
    sb.append("    \"xa_datasource_count\": ").append(m.xaDatasourceCount).append(",\n");
    sb.append("    \"xa_resource_count\": ").append(m.xaResourceCount).append(",\n");
    sb.append("    \"declarative_transaction_count\": ")
        .append(m.declarativeTransactionCount)
        .append(",\n");
    sb.append("    \"standard_transaction_manager_count\": ")
        .append(m.standardTransactionManagerCount)
        .append("\n");
    sb.append("  },\n");

    // Serialize Data Access metrics
    sb.append("  \"data_access\": {\n");
    sb.append("    \"jdbc_connections_count\": ").append(m.jdbcConnectionsCount).append(",\n");
    sb.append("    \"jpa_entities_count\": ").append(m.jpaEntitiesCount).append(",\n");
    sb.append("    \"hibernate_sessions_count\": ").append(m.hibernateSessionsCount).append(",\n");
    sb.append("    \"spring_data_repositories_count\": ")
        .append(m.springDataRepositoriesCount)
        .append("\n");
    sb.append("  },\n");

    // Serialize Security metrics
    sb.append("  \"security\": {\n");
    sb.append("    \"roles_allowed_count\": ").append(m.rolesAllowedCount).append(",\n");
    sb.append("    \"run_as_count\": ").append(m.runAsCount).append(",\n");
    sb.append("    \"user_in_role_count\": ").append(m.userInRoleCount).append(",\n");
    sb.append("    \"user_principal_count\": ").append(m.userPrincipalCount).append("\n");
    sb.append("  },\n");

    // Serialize Web Tier metrics
    sb.append("  \"web_tier\": {\n");
    sb.append("    \"servlets_count\": ").append(m.servletsCount).append(",\n");
    sb.append("    \"filters_count\": ").append(m.filtersCount).append(",\n");
    sb.append("    \"listeners_count\": ").append(m.listenersCount).append(",\n");
    sb.append("    \"jax_rs_endpoints_count\": ").append(m.jaxRsEndpointsCount).append(",\n");
    sb.append("    \"spring_controllers_count\": ").append(m.springControllersCount).append(",\n");
    sb.append("    \"struts_count\": ").append(m.strutsCount).append(",\n");
    sb.append("    \"jsf_count\": ").append(m.jsfCount).append(",\n");
    sb.append("    \"http_sessions_count\": ").append(m.httpSessionsCount).append("\n");
    sb.append("  },\n");

    // Serialize Advanced Container Features metrics
    sb.append("  \"advanced_features\": {\n");
    sb.append("    \"work_managers_count\": ").append(m.workmanagerCount).append(",\n");
    sb.append("    \"timers_count\": ").append(m.timersCount).append(",\n");
    sb.append("    \"web_services_count\": ").append(m.webServicesCount).append(",\n");
    sb.append("    \"jax_rpc_count\": ").append(m.jaxRpcCount).append(",\n");
    sb.append("    \"jax_ws_count\": ").append(m.jaxWsCount).append(",\n");
    sb.append("    \"batch_processing_count\": ").append(m.batchProcessingCount).append(",\n");
    sb.append("    \"jmx_mbeans_count\": ").append(m.jmxMbeansCount).append("\n");
    sb.append("  },\n");

    // Serialize Cloud-Unfriendly Patterns metrics
    sb.append("  \"cloud_unfriendly_patterns\": {\n");
    sb.append("    \"raw_threads_count\": ").append(m.rawThreadsCount).append(",\n");
    sb.append("    \"native_processes_count\": ").append(m.nativeProcessesCount).append(",\n");
    sb.append("    \"direct_sockets_count\": ").append(m.directSocketsCount).append(",\n");
    sb.append("    \"jaas_login_modules_count\": ").append(m.jaasLoginModulesCount).append(",\n");
    sb.append("    \"specific_proxies_count\": ").append(m.specificProxiesCount).append(",\n");
    sb.append("    \"file_io_count\": ").append(m.fileIoCount).append(",\n");
    sb.append("    \"rmi_corba_count\": ").append(m.rmiCorbaCount).append(",\n");
    sb.append("    \"java_mail_count\": ").append(m.javaMailCount).append("\n");
    sb.append("  }\n");

    sb.append("}");
    return sb.toString();
  }

  /**
   * AST Visitor implementation that inspects Java language syntax nodes to populate {@link
   * Metrics}.
   *
   * <p>Overrides OpenRewrite visitor hooks for package imports, annotations, method invocations,
   * class/interface declarations, constructors, and variable declarations.
   */
  private static class MetricsVisitor extends JavaVisitor<Metrics> {

    /**
     * Inspects package import statements to identify library dependencies and framework usage.
     *
     * @param imp The AST import node being visited.
     * @param m The metrics container to increment.
     * @return The visited AST node.
     */
    @Override
    public J visitImport(J.Import imp, Metrics m) {
      String pkg = imp.getPackageName();
      if (pkg != null) {
        // Detect WebLogic specific APIs
        if (pkg.startsWith("weblogic")) {
          m.wlsImportsCount++;
        }
        if (pkg.startsWith("weblogic.logging")) {
          m.loggingCount++;
        }
        if (pkg.startsWith("weblogic.security")) {
          m.securityCount++;
        }
        if (pkg.startsWith("weblogic.transaction")) {
          m.transactionCount++;
        }
        if (pkg.startsWith("weblogic.work")) {
          m.workmanagerCount++;
        }
        if (pkg.startsWith("weblogic.jws")) {
          m.jwsApiCount++;
        }

        // Detect Oracle Coherence distributed caching
        if (pkg.startsWith("com.tangosol") || pkg.startsWith("coherence")) {
          m.coherenceCount++;
        }

        // Detect messaging and web services APIs
        if (pkg.startsWith("javax.jms") || pkg.startsWith("jakarta.jms")) {
          m.jmsImportsCount++;
        }
        if (pkg.startsWith("javax.xml.rpc")) {
          m.jaxRpcCount++;
        }
        if (pkg.startsWith("javax.jws") || pkg.startsWith("jakarta.jws")) {
          m.jaxWsCount++;
        }

        // Detect batch processing and legacy remoting
        if (pkg.startsWith("javax.batch") || pkg.startsWith("org.springframework.batch")) {
          m.batchProcessingCount++;
        }
        if (pkg.startsWith("java.rmi") || pkg.startsWith("javax.rmi")) {
          m.rmiCorbaCount++;
        }
        if (pkg.startsWith("javax.mail") || pkg.startsWith("jakarta.mail")) {
          m.javaMailCount++;
        }

        // Detect legacy presentation frameworks
        if (pkg.startsWith("org.apache.struts")) {
          m.strutsCount++;
        }
        if (pkg.startsWith("javax.faces") || pkg.startsWith("jakarta.faces")) {
          m.jsfCount++;
        }
      }
      return super.visitImport(imp, m);
    }

    /**
     * Inspects Java annotations to identify EJB types, declarative transactions, JPA entities,
     * security roles, servlets, web filters, and REST/SOAP endpoints.
     *
     * @param annotation The AST annotation node being visited.
     * @param m The metrics container to increment.
     * @return The visited AST node.
     */
    @Override
    public J visitAnnotation(J.Annotation annotation, Metrics m) {
      String name = annotation.getSimpleName();

      // EJB component annotations
      if (name.equals("Stateless")) {
        m.statelessCount++;
      }
      if (name.equals("Stateful")) {
        m.statefulCount++;
      }
      if (name.equals("Singleton")) {
        m.singletonCount++;
      }
      if (name.equals("MessageDriven")) {
        m.mdbCount++;
      }

      // Declarative transaction and persistence annotations
      if (name.equals("Transactional") || name.equals("TransactionAttribute")) {
        m.declarativeTransactionCount++;
      }
      if (name.equals("Entity")) {
        m.jpaEntitiesCount++;
      }

      // Security and authorization annotations
      if (name.equals("RolesAllowed")) {
        m.rolesAllowedCount++;
      }
      if (name.equals("RunAs")) {
        m.runAsCount++;
      }

      // Web tier and servlet container annotations
      if (name.equals("WebServlet")) {
        m.servletsCount++;
      }
      if (name.equals("WebFilter")) {
        m.filtersCount++;
      }
      if (name.equals("WebListener")) {
        m.listenersCount++;
      }

      // Modern REST controllers and JSF backing beans
      if (name.equals("Path") || name.equals("GET") || name.equals("POST") || name.equals("PUT")) {
        m.jaxRsEndpointsCount++;
      }
      if (name.equals("Controller") || name.equals("RestController")) {
        m.springControllersCount++;
      }
      if (name.equals("ManagedBean")) {
        m.jsfCount++;
      }

      // SOAP Web Service annotations
      if (name.equals("WebService") || name.equals("WebMethod")) {
        m.webServicesCount++;
      }

      return super.visitAnnotation(annotation, m);
    }

    /**
     * Inspects method invocations to detect JNDI lookups, HTTP session state access, programmatic
     * security checks, and native OS process execution.
     *
     * @param method The AST method invocation node being visited.
     * @param m The metrics container to increment.
     * @return The visited AST node.
     */
    @Override
    public J visitMethodInvocation(J.MethodInvocation method, Metrics m) {
      String name = method.getSimpleName();
      if (name.equals("lookup")) {
        m.lookupsCount++;
      }
      if (name.equals("getSession")) {
        m.httpSessionsCount++;
      }
      if (name.equals("isUserInRole")) {
        m.userInRoleCount++;
      }
      if (name.equals("getUserPrincipal")) {
        m.userPrincipalCount++;
      }
      if (name.equals("exec")) {
        m.nativeProcessesCount++;
      }
      return super.visitMethodInvocation(method, m);
    }

    /**
     * Inspects class and interface declarations to identify legacy EJB 2.x BMP/CMP entity beans,
     * MDBs, servlet filters, listeners, JAAS login modules, and WebLogic specific cluster servlets.
     *
     * @param classDecl The AST class declaration node being visited.
     * @param m The metrics container to increment.
     * @return The visited AST node.
     */
    @Override
    public J visitClassDeclaration(J.ClassDeclaration classDecl, Metrics m) {
      // Check implemented interfaces
      if (classDecl.getImplements() != null) {
        for (TypeTree type : classDecl.getImplements()) {
          String ts = type.toString();
          if (ts.contains("EntityBean")) {
            m.entityBeanCount++;
          }
          if (ts.contains("MessageDrivenBean")) {
            m.mdbCount++;
          }
          if (ts.contains("SessionBean")) {
            if ("Stateful".equals(getSessionEJBType(classDecl))) {
              m.statefulCount++;
            } else {
              m.statelessCount++;
            }
          }
          if (ts.contains("Filter")) {
            m.filtersCount++;
          }
          if (ts.contains("ServletContextListener")) {
            m.listenersCount++;
          }
          if (ts.contains("LoginModule")) {
            m.jaasLoginModulesCount++;
          }
        }
      }

      // Check extended superclasses
      if (classDecl.getExtends() != null) {
        String ts = classDecl.getExtends().toString();
        if (ts.contains("EntityBean")) {
          m.entityBeanCount++;
        }
        if (ts.contains("GenericSessionBean") || ts.contains("SessionBean")) {
          if ("Stateful".equals(getSessionEJBType(classDecl))) {
            m.statefulCount++;
          } else {
            m.statelessCount++;
          }
        }
        if (ts.contains("GenericMessageDrivenBean") || ts.contains("MessageDrivenBean")) {
          m.mdbCount++;
        }
        if (ts.contains("EJBHome")
            || ts.contains("EJBLocalHome")
            || ts.contains("EJBObject")
            || ts.contains("EJBLocalObject")) {
          m.ejb2xHomeInterfacesCount++;
        }
        if (ts.contains("HttpServlet")) {
          m.servletsCount++;
        }
        if (ts.contains("UsernamePasswordLoginModule")) {
          m.jaasLoginModulesCount++;
        }
        if (ts.contains("HttpClusterServlet") || ts.contains("HttpProxyServlet")) {
          m.specificProxiesCount++;
        }
      }
      return super.visitClassDeclaration(classDecl, m);
    }

    /**
     * Inspects constructor invocations (new object instantiations) to detect JNDI InitialContext
     * creations, raw thread spawning, direct sockets, local filesystem I/O, and native process
     * builders.
     *
     * @param newClass The AST constructor invocation node being visited.
     * @param m The metrics container to increment.
     * @return The visited AST node.
     */
    @Override
    public J visitNewClass(J.NewClass newClass, Metrics m) {
      String type = newClass.getClazz() != null ? newClass.getClazz().toString() : "";
      if (type.contains("InitialContext")) {
        m.initialContextCount++;
      }
      if (type.contains("Thread")) {
        m.rawThreadsCount++;
      }
      if (type.contains("Socket") || type.contains("ServerSocket")) {
        m.directSocketsCount++;
      }
      if (type.contains("FileOutputStream")
          || type.contains("FileWriter")
          || type.contains("RandomAccessFile")) {
        m.fileIoCount++;
      }
      if (type.contains("ProcessBuilder")) {
        m.nativeProcessesCount++;
      }
      return super.visitNewClass(newClass, m);
    }

    /**
     * Inspects variable declarations to detect WebLogic transaction managers, programmatic user
     * transactions, JMS producers/consumers/resources, XA datasources, JDBC connections,
     * Hibernate/HTTP sessions, timers, and JMX MBeans.
     *
     * @param multiVariable The AST variable declaration node being visited.
     * @param m The metrics container to increment.
     * @return The visited AST node.
     */
    @Override
    public J visitVariableDeclarations(J.VariableDeclarations multiVariable, Metrics m) {
      String type =
          multiVariable.getTypeExpression() != null
              ? multiVariable.getTypeExpression().toString()
              : "";
      if (type.contains("TransactionManager") || type.contains("TxHelper")) {
        m.wlsTransactionManagerCount++;
      }
      if (type.contains("UserTransaction")) {
        m.wlsUserTransactionCount++;
      }
      if (type.contains("MessageProducer")
          || type.contains("QueueSender")
          || type.contains("TopicPublisher")) {
        m.jmsProducerCount++;
      }
      if (type.contains("MessageConsumer")
          || type.contains("QueueReceiver")
          || type.contains("TopicSubscriber")) {
        m.jmsConsumerCount++;
      }
      if (type.contains("Queue")) {
        m.jmsQueueCount++;
      }
      if (type.contains("Topic")) {
        m.jmsTopicCount++;
      }
      if (type.contains("XADataSource")) {
        m.xaDatasourceCount++;
      }
      if (type.contains("XAResource")) {
        m.xaResourceCount++;
      }
      if (type.contains("Connection") || type.contains("DataSource")) {
        m.jdbcConnectionsCount++;
      }
      if (type.contains("Session") && type.contains("hibernate")) {
        m.hibernateSessionsCount++;
      }
      if (type.contains("HttpSession")) {
        m.httpSessionsCount++;
      }
      if (type.contains("TimerService") || type.contains("Timer")) {
        m.timersCount++;
      }
      if (type.contains("MBeanServer")) {
        m.jmxMbeansCount++;
      }
      return super.visitVariableDeclarations(multiVariable, m);
    }

    private String getSessionEJBType(J.ClassDeclaration classDecl) {
      if (classDecl.getPrefix() == null || classDecl.getPrefix().getComments() == null) {
        return "Stateless";
      }
      java.util.regex.Pattern pattern =
          java.util.regex.Pattern.compile(
              "@ejbgen:session[^\\*]*type\\s*=\\s*Stateful", java.util.regex.Pattern.DOTALL);
      for (org.openrewrite.java.tree.Comment comment : classDecl.getPrefix().getComments()) {
        String text = comment.toString();
        if (pattern.matcher(text).find()) {
          return "Stateful";
        }
      }
      return "Stateless";
    }
  }
}
