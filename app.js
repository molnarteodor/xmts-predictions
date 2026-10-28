// ================= CONFIGURARE SUPABASE (FĂRĂ PAROLE ÎN CLIENT) =================
const SUPABASE_URL = "https://edlfqiruegrmxcuubmil.supabase.co";
const SUPABASE_KEY = "sb_publishable_b8npaox4JSEHkQzGC-SAjg_UHm_bOBE";
const SUPABASE_EDGE_URL = "https://edlfqiruegrmxcuubmil.supabase.co/functions/v1/create-user-admin";

const isSupabaseConfigured = () => SUPABASE_URL.startsWith("https://") && SUPABASE_KEY.length > 20;

function sbHeaders() {
  return {
    "apikey": SUPABASE_KEY,
    "Authorization": "Bearer " + SUPABASE_KEY,
    "Content-Type": "application/json",
    "Prefer": "return=representation"
  };
}

let usersList = [];
let currentUser = null;
let adminSessionPass = null;

const LEAGUES = [
  {slug:"eng.1",name:"Premier League",icon:"🏴󠁧󠁢󠁥󠁮󠁧󠁿",cat:"nat",cBase:10.3,kBase:3.8,gBase:2.82,rho:-0.07},
  {slug:"esp.1",name:"La Liga",icon:"🇪🇸",cat:"nat",cBase:9.3,kBase:4.7,gBase:2.52,rho:-0.11},
  {slug:"ita.1",name:"Serie A",icon:"🇮🇹",cat:"nat",cBase:9.5,kBase:4.3,gBase:2.56,rho:-0.12},
  {slug:"ger.1",name:"Bundesliga",icon:"🇩🇪",cat:"nat",cBase:9.8,kBase:3.7,gBase:3.02,rho:-0.05},
  {slug:"fra.1",name:"Ligue 1",icon:"🇫🇷",cat:"nat",cBase:9.2,kBase:3.9,gBase:2.64,rho:-0.09},
  {slug:"rou.1",name:"SuperLiga României",icon:"🇷🇴",cat:"nat",cBase:8.7,kBase:4.5,gBase:2.38,rho:-0.13},
  {slug:"ned.1",name:"Eredivisie",icon:"🇳🇱",cat:"nat",cBase:10.4,kBase:3.1,gBase:3.06,rho:-0.04},
  {slug:"por.1",name:"Primeira Liga",icon:"🇵🇹",cat:"nat",cBase:9.7,kBase:4.6,gBase:2.55,rho:-0.10},
  {slug:"tur.1",name:"Süper Lig",icon:"🇹🇷",cat:"nat",cBase:9.5,kBase:4.8,gBase:2.74,rho:-0.08},
  {slug:"gre.1",name:"Super League Grecia",icon:"🇬🇷",cat:"nat",cBase:8.8,kBase:4.7,gBase:2.42,rho:-0.12},
  {slug:"uefa.champions",name:"UEFA Champions League",icon:"🏆",cat:"eu",cBase:9.9,kBase:4.0,gBase:2.86,rho:-0.07},
  {slug:"uefa.europa",name:"UEFA Europa League",icon:"🟠",cat:"eu",cBase:9.6,kBase:4.3,gBase:2.72,rho:-0.08},
  {slug:"uefa.europa.conf",name:"UEFA Conference League",icon:"🟢",cat:"eu",cBase:9.3,kBase:4.4,gBase:2.64,rho:-0.09}
];

const CLUB_POWER = [
  {k:"manchester city",p:0.55},{k:"real madrid",p:0.55},{k:"bayern",p:0.54},{k:"barcelona",p:0.52},
  {k:"liverpool",p:0.50},{k:"inter",p:0.48},{k:"arsenal",p:0.48},{k:"paris saint-germain",p:0.48},{k:"psg",p:0.48},
  {k:"leverkusen",p:0.42},{k:"napoli",p:0.44},{k:"atletico",p:0.40},{k:"atlético",p:0.40},{k:"dortmund",p:0.38},
  {k:"juventus",p:0.38},{k:"milan",p:0.36},{k:"atalanta",p:0.39},{k:"chelsea",p:0.36},{k:"tottenham",p:0.32},
  {k:"aston villa",p:0.31},{k:"newcastle",p:0.30},{k:"manchester united",p:0.26},{k:"leipzig",p:0.34},
  {k:"sporting",p:0.44},{k:"benfica",p:0.42},{k:"porto",p:0.40},{k:"psv",p:0.44},{k:"feyenoord",p:0.34},{k:"ajax",p:0.32},
  {k:"galatasaray",p:0.42},{k:"fenerbahce",p:0.40},{k:"fenerbahçe",p:0.40},{k:"besiktas",p:0.28},
  {k:"olympiacos",p:0.34},{k:"paok",p:0.31},{k:"panathinaikos",p:0.29},{k:"aek",p:0.29},
  {k:"lazio",p:0.30},{k:"roma",p:0.29},{k:"fiorentina",p:0.27},{k:"bologna",p:0.20},{k:"torino",p:0.12},
  {k:"athletic",p:0.28},{k:"villarreal",p:0.27},{k:"real sociedad",p:0.24},{k:"betis",p:0.22},{k:"girona",p:0.18},
  {k:"frankfurt",p:0.27},{k:"stuttgart",p:0.27},{k:"monaco",p:0.32},{k:"marseille",p:0.31},{k:"lille",p:0.28},{k:"lyon",p:0.25},
  {k:"brighton",p:0.22},{k:"fulham",p:0.15},{k:"bournemouth",p:0.14},{k:"west ham",p:0.14},{k:"braga",p:0.25},
  {k:"fcsb",p:0.32},{k:"cfr cluj",p:0.28},{k:"universitatea craiova",p:0.26},{k:"craiova",p:0.26},
  {k:"universitatea cluj",p:0.22},{k:"u cluj",p:0.22},{k:"rapid",p:0.22},{k:"dinamo",p:0.16},{k:"sepsi",p:0.12},{k:"farul",p:0.10},
  {k:"slobozia",p:-0.24},{k:"botoșani",p:-0.20},{k:"botosani",p:-0.20},{k:"buzău",p:-0.25},{k:"buzau",p:-0.25},{k:"poli iași",p:-0.18},{k:"ermannstadt",p:-0.10},
  {k:"monza",p:-0.26},{k:"lecce",p:-0.26},{k:"venezia",p:-0.28},{k:"empoli",p:-0.20},{k:"cagliari",p:-0.20},
  {k:"verona",p:-0.22},{k:"parma",p:-0.16},{k:"como",p:-0.14},{k:"genoa",p:-0.16},{k:"udinese",p:-0.06},{k:"sassuolo",p:-0.12},
  {k:"valladolid",p:-0.28},{k:"las palmas",p:-0.24},{k:"leganes",p:-0.22},{k:"espanyol",p:-0.22},{k:"getafe",p:-0.14},{k:"alaves",p:-0.18},
  {k:"southampton",p:-0.30},{k:"ipswich",p:-0.28},{k:"leicester",p:-0.24},{k:"wolves",p:-0.18},{k:"everton",p:-0.14},{k:"crystal palace",p:-0.08},
  {k:"kiel",p:-0.28},{k:"bochum",p:-0.28},{k:"st. pauli",p:-0.24},{k:"heidenheim",p:-0.20},{k:"augsburg",p:-0.14},
  {k:"le havre",p:-0.26},{k:"angers",p:-0.26},{k:"montpellier",p:-0.24},{k:"saint-etienne",p:-0.22},{k:"nantes",p:-0.18},{k:"auxerre",p:-0.16}
];

let currentNav = "meciuri", selectedDate = "", selectedLeague = "ALL", cacheByDate = {}, europaMatches = [], targetTicketOdds = 5;
let customBudget = 100;
let isGeneratingTicket = false;
let currentTicketPicks = [], currentTicketTotalOdd = 1.0;
let project = { initial_bankroll: 500.0, target_bankroll: 800.0, bankroll: 500.0, bets: [] };

let vipChatMessages = [
  { sender: 'joe', text: 'Salut, șefu! Urcă o poză pe 📷 (bilet sau statistici) și îți dau verdictul scurt pe loc, sau întreabă-mă de orice meci!' }
];
let lastUploadedImage = null;

const roDateStr = d => d.toLocaleDateString("sv-SE", { timeZone: "Europe/Bucharest" });
const roTimeStr = d => d.toLocaleTimeString("ro-RO", { timeZone: "Europe/Bucharest", hour: "2-digit", minute: "2-digit" });

function hasJoeAccess() {
  return currentUser && (currentUser.role === "vip" || currentUser.role === "admin");
}

function isAdmin() {
  return currentUser && currentUser.role === "admin";
}

function applyRolePermissions() {
  const joeBtn = document.getElementById("nav-proiect");
  const bankBtn = document.getElementById("topBankBtn");
  const adminBtn = document.getElementById("nav-admin");
  const titleEl = document.getElementById("hudAppTitle");

  if (hasJoeAccess()) {
    joeBtn.style.display = "flex";
    bankBtn.style.display = "block";
    titleEl.innerText = "JOE PREZICE";
  } else {
    joeBtn.style.display = "none";
    bankBtn.style.display = "none";
    titleEl.innerText = "JOE PREZICE";
    if (currentNav === "proiect" || currentNav === "admin") currentNav = "meciuri";
  }

  adminBtn.style.display = isAdmin() ? "flex" : "none";
}

// ================= AUTENTIFICARE 100% SERVER-SIDE (RPC SUPABASE) =================
async function attemptLogin() {
  const u = document.getElementById("loginUser").value.trim().toLowerCase();
  const p = document.getElementById("loginPass").value.trim();
  const errEl = document.getElementById("loginErr");
  const btnEl = document.getElementById("loginSubmitBtn");
  errEl.style.display = "none";

  if (!u || !p) {
    errEl.innerText = "Introdu utilizatorul și parola!";
    errEl.style.display = "block";
    return;
  }

  if (btnEl) btnEl.innerText = "⏳ SE VERIFICĂ...";

  try {
    const r = await fetch(`${SUPABASE_URL}/rest/v1/rpc/verify_user_login`, {
      method: "POST",
      headers: sbHeaders(),
      body: JSON.stringify({ p_username: u, p_password: p })
    });

    const data = await r.json();
    if (btnEl) btnEl.innerText = "🔐 AUTENTIFICARE";

    if (!r.ok || !data || !data.ok) {
      errEl.innerText = (data && data.error) ? data.error : "Date de logare incorecte!";
      errEl.style.display = "block";
      return;
    }

    currentUser = {
      username: data.username,
      role: data.role,
      expires_at: data.expires_at
    };

    if (currentUser.role === "admin") {
      adminSessionPass = p;
      sessionStorage.setItem("xmts_adm_token", p);
      await fetchAdminUsersList();
    }

    localStorage.setItem("xmts_logged_user", JSON.stringify(currentUser));
    document.getElementById("loginScreen").style.display = "none";
    applyRolePermissions();
    renderViewport();
  } catch (e) {
    if (btnEl) btnEl.innerText = "🔐 AUTENTIFICARE";
    errEl.innerText = "Eroare de conexiune cu serverul!";
    errEl.style.display = "block";
  }
}

async function fetchAdminUsersList() {
  if (!isAdmin() || !adminSessionPass) return;
  try {
    const r = await fetch(`${SUPABASE_URL}/rest/v1/rpc/admin_list_users`, {
      method: "POST",
      headers: sbHeaders(),
      body: JSON.stringify({ p_admin_user: currentUser.username, p_admin_pass: adminSessionPass })
    });
    if (r.ok) {
      const list = await r.json();
      if (Array.isArray(list)) usersList = list;
    }
  } catch (e) { console.error(e); }
}

function logoutUser() {
  currentUser = null;
  adminSessionPass = null;
  usersList = [];
  localStorage.removeItem("xmts_logged_user");
  sessionStorage.removeItem("xmts_adm_token");
  document.getElementById("loginUser").value = "";
  document.getElementById("loginPass").value = "";
  document.getElementById("loginScreen").style.display = "flex";
}

function calculateExpiresAt(duration) {
  const now = new Date();
  if (duration === 'trial') now.setDate(now.getDate() + 2);
  else if (duration === '1_month') now.setMonth(now.getMonth() + 1);
  else if (duration === '3_months') now.setMonth(now.getMonth() + 3);
  else if (duration === '6_months') now.setMonth(now.getMonth() + 6);
  else if (duration === '1_year') now.setFullYear(now.getFullYear() + 1);
  else now.setMonth(now.getMonth() + 1);
  return now.toISOString();
}

function formatExpiryDate(isoStr) {
  if (!isoStr) return "Permanent / Nelimitat";
  const d = new Date(isoStr);
  return d.toLocaleDateString("ro-RO", { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

async function createNewUser() {
  const rawUsername = document.getElementById("newUsername").value.trim().toLowerCase();
  const password = document.getElementById("newPassword").value.trim();
  const tier = document.getElementById("newRole").value;
  const duration = document.getElementById("newDuration").value;
  const adminSecret = document.getElementById("adminSecretInput").value.trim();
  const resultMsg = document.getElementById("formResultMsg");

  if (!rawUsername || !password || !adminSecret) {
    if(resultMsg) {
      resultMsg.style.color = "var(--neon-red)";
      resultMsg.innerText = "Completează toate câmpurile obligatorii și parola secretă de admin!";
    }
    return;
  }

  const email = rawUsername.includes('@') ? rawUsername : `${rawUsername}@joeprezice.online`;
  let mappedRole = tier === 'standard' ? 'basic' : (tier === 'vip' ? 'vip' : 'admin');
  const expiresAt = calculateExpiresAt(duration);

  if(resultMsg) {
    resultMsg.style.color = "var(--neon-gold)";
    resultMsg.innerText = "Se creează contul securizat și se setează abonamentul...";
  }

  try {
    const response = await fetch(SUPABASE_EDGE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, tier, duration, adminSecret })
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Eroare necunoscută");

    if (isSupabaseConfigured() && adminSessionPass) {
      await fetch(`${SUPABASE_URL}/rest/v1/rpc/admin_manage_user`, {
        method: "POST",
        headers: sbHeaders(),
        body: JSON.stringify({
          p_admin_user: currentUser.username,
          p_admin_pass: adminSessionPass,
          p_action: "upsert",
          p_target_user: rawUsername,
          p_target_pass: password,
          p_target_role: mappedRole,
          p_target_expires: expiresAt
        })
      });
      await fetchAdminUsersList();
    }

    if(resultMsg) {
      resultMsg.style.color = "var(--neon-green)";
      resultMsg.innerText = `✅ Contul "${rawUsername}" a fost creat cu succes!`;
    }
    copyText(`Cont creat!\nUtilizator: ${rawUsername}\nParolă: ${password}`);
    setTimeout(() => { renderViewport(); }, 1000);

  } catch (err) {
    if(resultMsg) {
      resultMsg.style.color = "var(--neon-red)";
      resultMsg.innerText = "Eroare: " + err.message;
    }
  }
}

async function removeUser(uname) {
  if (uname === "teodor") { alert("Contul principal de Admin nu poate fi șters!"); return; }
  if (!confirm(`Ștergi utilizatorul ${uname}?`)) return;

  if (isSupabaseConfigured() && adminSessionPass) {
    try {
      await fetch(`${SUPABASE_URL}/rest/v1/rpc/admin_manage_user`, {
        method: "POST",
        headers: sbHeaders(),
        body: JSON.stringify({
          p_admin_user: currentUser.username,
          p_admin_pass: adminSessionPass,
          p_action: "delete",
          p_target_user: uname
        })
      });
      await fetchAdminUsersList();
    } catch (e) { console.error(e); }
  }
  renderViewport();
}

function copyText(txt) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(txt).catch(() => fallbackCopy(txt));
  } else {
    fallbackCopy(txt);
  }
  const t = document.getElementById("toastMsg");
  t.style.display = "block";
  setTimeout(() => { t.style.display = "none"; }, 1800);
}

function fallbackCopy(txt) {
  const ta = document.createElement("textarea");
  ta.value = txt; document.body.appendChild(ta); ta.select();
  document.execCommand("copy"); document.body.removeChild(ta);
}

function copyCurrentTicket() {
  const nl = String.fromCharCode(10);
  const header = "🎟️ JOE PREZICE - BILETUL ZILEI (" + selectedDate + ") — Cotă Totală: @" + currentTicketTotalOdd.toFixed(2) + " | Buget: " + customBudget + " RON";
  const lines = currentTicketPicks.map((m, i) => (i + 1) + ". " + m.home + " vs " + m.away + " -> " + m.pick + " (@" + m.odd.toFixed(2) + ")");
  copyText([header, ...lines].join(nl));
}

// ================= EXTRAGERE DATE REALE ȘI ANALIZĂ MATEMATICĂ =================

function extractMarketOdds(comp) {
  if (!comp.odds || !Array.isArray(comp.odds) || comp.odds.length === 0) return null;
  const oddObj = comp.odds.find(o => o && (o.homeTeamOdds || o.overUnder)) || comp.odds[0];
  if (!oddObj) return null;

  const mlToDec = (ml) => {
    const n = parseFloat(ml);
    if (isNaN(n) || n === 0) return null;
    return n > 0 ? 1 + (n / 100) : 1 + (100 / Math.abs(n));
  };

  let mktPH = null, mktPD = null, mktPA = null, decH = null, decD = null, decA = null;
  if (oddObj.homeTeamOdds && oddObj.awayTeamOdds) {
    decH = mlToDec(oddObj.homeTeamOdds.moneyLine);
    decA = mlToDec(oddObj.awayTeamOdds.moneyLine);
    decD = oddObj.drawOdds ? mlToDec(oddObj.drawOdds.moneyLine) : null;
    if (decH && decA) {
      const effD = decD || 3.35;
      const invH = 1 / decH, invD = 1 / effD, invA = 1 / decA;
      const overround = invH + invD + invA;
      mktPH = invH / overround;
      mktPD = invD / overround;
      mktPA = invA / overround;
    }
  }

  const ouLine = oddObj.overUnder ? parseFloat(oddObj.overUnder) : null;
  return { mktPH, mktPD, mktPA, decH, decD, decA, ouLine };
}

function getClubBasePower(name) {
  const low = (name || "").toLowerCase();
  for (let c of CLUB_POWER) if (low.includes(c.k)) return c.p;
  return 0;
}

function extractTeamStrength(compObj, isHome, teamName) {
  let formScore = 0, overallScore = 0, venueScore = 0, formDisplay = "";
  let winsRate5 = 2.0, drawsRate5 = 1.4, lossesRate5 = 1.6, drawRatio = 0.26;
  let hasRealRecord = false, hasRealForm = false;

  const clubPower = getClubBasePower(teamName || (compObj.team && (compObj.team.displayName || compObj.team.name)) || "");

  if (compObj.records && Array.isArray(compObj.records)) {
    const parseRec = (rec) => {
      if (!rec || !rec.summary) return null;
      const parts = rec.summary.split("-").map(x => parseInt(x, 10));
      if (parts.length === 3 && !isNaN(parts[0])) {
        const [w, d, l] = parts;
        const tot = w + d + l;
        if (tot > 0) return { w, d, l, tot, ppg: (w * 3 + d) / tot };
      }
      return null;
    };

    const totalRec = parseRec(compObj.records.find(r => r.type === "total") || compObj.records[0]);
    const venueRec = parseRec(compObj.records.find(r => 
      r.type === (isHome ? "home" : "road") || 
      (r.name && r.name.toLowerCase() === (isHome ? "home" : "away"))
    ));

    if (totalRec) {
      hasRealRecord = true;
      const reliability = Math.min(1.0, totalRec.tot / (totalRec.tot + 3));
      overallScore = (totalRec.ppg - 1.35) * 0.62 * reliability;
      formDisplay = `${totalRec.w}V-${totalRec.d}E-${totalRec.l}Î`;
      winsRate5 = (totalRec.w / totalRec.tot) * 5;
      drawsRate5 = (totalRec.d / totalRec.tot) * 5;
      lossesRate5 = (totalRec.l / totalRec.tot) * 5;
      drawRatio = totalRec.d / totalRec.tot;
    }

    if (venueRec && venueRec.tot >= 2) {
      const venueRel = Math.min(1.0, venueRec.tot / (venueRec.tot + 3));
      const expectedVenuePpg = isHome ? 1.50 : 1.20;
      venueScore = (venueRec.ppg - expectedVenuePpg) * 0.50 * venueRel;
    }
  }

  if (compObj.form && typeof compObj.form === "string") {
    const rawForm = compObj.form.toUpperCase().replace(/[^WDL]/g, "").slice(-5);
    if (rawForm.length >= 3) {
      hasRealForm = true;
      let fW = 0, fD = 0, fL = 0;
      formDisplay = formDisplay ? `${rawForm} (${formDisplay})` : rawForm;
      const weights = [0.60, 0.80, 1.0, 1.25, 1.50];
      for (let i = 0; i < rawForm.length; i++) {
        const ch = rawForm[i];
        if (ch === "W") fW++;
        else if (ch === "D") fD++;
        else if (ch === "L") fL++;
        const w = weights[i + (5 - rawForm.length)] || 1.0;
        formScore += (ch === "W" ? 0.075 : (ch === "D" ? 0.0 : -0.075)) * w;
      }
      const scale5 = 5 / rawForm.length;
      if (hasRealRecord) {
        winsRate5 = winsRate5 * 0.50 + (fW * scale5) * 0.50;
        drawsRate5 = drawsRate5 * 0.50 + (fD * scale5) * 0.50;
        lossesRate5 = lossesRate5 * 0.50 + (fL * scale5) * 0.50;
      } else {
        winsRate5 = fW * scale5;
        drawsRate5 = fD * scale5;
        lossesRate5 = fL * scale5;
        drawRatio = fD / rawForm.length;
      }
    }
  }

  const hasData = hasRealRecord || hasRealForm || clubPower !== 0;
  if (!formDisplay) formDisplay = clubPower !== 0 ? "Rating Lot Activ" : "Date limitate";

  let tablePerf = overallScore;
  if (venueScore !== 0) tablePerf = overallScore * 0.62 + venueScore * 0.38;

  let statsStrength = hasRealRecord
    ? (hasRealForm ? tablePerf * 0.68 + formScore * 0.32 : tablePerf)
    : formScore;

  let totalStrength = statsStrength;
  if (clubPower !== 0 && (hasRealRecord || hasRealForm)) {
    totalStrength = statsStrength * 0.45 + clubPower * 0.55;
  } else if (clubPower !== 0) {
    totalStrength = clubPower * 0.85;
  }

  return {
    score: totalStrength,
    clubPower,
    winsCount: +winsRate5.toFixed(2),
    drawsCount: +drawsRate5.toFixed(2),
    lossesCount: +lossesRate5.toFixed(2),
    drawRatio,
    hasData,
    formDisplay
  };
}

function getDatesList() {
  const list = [], now = new Date(), labels = {"-1":"Ieri","0":"Azi","1":"Mâine"};
  for (let i = -1; i <= 5; i++) {
    const d = new Date(now.getTime() + i * 86400000), iso = roDateStr(d), p = iso.split("-"), s = p[2] + "." + p[1];
    list.push({ iso, ymd: iso.replace(/-/g, ""), label: labels[String(i)] ? `${labels[String(i)]} (${s})` : s });
  }
  return list;
}

function poissonPmf(k, lam) {
  let f = 1;
  for (let i = 2; i <= k; i++) f *= i;
  return Math.exp(-lam) * Math.pow(lam, k) / f;
}

function poissonOverProb(line, lam) {
  const minK = Math.floor(line) + 1;
  let cdf = 0;
  for (let k = 0; k < minK; k++) cdf += poissonPmf(k, lam);
  return Math.max(0.05, Math.min(0.95, 1 - cdf));
}

function selectOptimalStatLine(expVal, overLines, underLines) {
  const options = [];
  for (let l of overLines) {
    const p = poissonOverProb(l, expVal);
    if (p >= 0.56 && p <= 0.80) {
      options.push({ label: `Peste ${l}`, prob: Math.round(p * 100), score: p });
    }
  }
  for (let l of underLines) {
    const p = 1 - poissonOverProb(l, expVal);
    if (p >= 0.58 && p <= 0.80) {
      options.push({ label: `Sub ${l}`, prob: Math.round(p * 100), score: p * 0.97 });
    }
  }
  if (!options.length) {
    const midLine = overLines[1] || overLines[0];
    const p = poissonOverProb(midLine, expVal);
    return p >= 0.50 
      ? { label: `Peste ${midLine}`, prob: Math.round(p * 100) }
      : { label: `Sub ${midLine + 1}`, prob: Math.round((1 - poissonOverProb(midLine + 1, expVal)) * 100) };
  }
  options.sort((a, b) => b.score - a.score);
  return options[0];
}

function dixonColesTau(h, a, lamH, lamA, rho = -0.09) {
  if (h === 0 && a === 0) return Math.max(0.5, 1 - lamH * lamA * rho);
  if (h === 0 && a === 1) return Math.max(0.5, 1 + lamH * rho);
  if (h === 1 && a === 0) return Math.max(0.5, 1 + lamA * rho);
  if (h === 1 && a === 1) return Math.max(0.5, 1 - rho);
  return 1.0;
}

function calculateSmartStake(bankroll, m) {
  let pct = 0.04;
  if (m.edgePct && m.edgePct > 2) {
    const p = m.prob / 100;
    const b = Math.max(0.25, m.odd - 1);
    const kelly = ((p * b - (1 - p)) / b) * 0.30;
    pct = Math.max(0.03, Math.min(0.08, kelly));
  } else {
    if (m.prob >= 66) pct = 0.07;
    else if (m.prob >= 60) pct = 0.06;
    else if (m.prob >= 55) pct = 0.05;
    else pct = 0.04;
  }

  if (m.lowData) pct = Math.min(pct, 0.03);

  const rawStake = bankroll * pct;
  return {
    stake: Math.max(10, Math.round(rawStake / 5) * 5),
    pct: Math.round(pct * 100)
  };
}

function analyzeMatch(ev, lg) {
  const comp = ev.competitions[0], cs = comp.competitors;
  const home = cs.find(c => c.homeAway === "home") || cs[0], away = cs.find(c => c.homeAway === "away") || cs[1];
  const hName = home.team.displayName || home.team.name, aName = away.team.displayName || away.team.name;
  const dt = new Date(comp.date || ev.date), stState = (comp.status && comp.status.type && comp.status.type.state) || "pre";
  const hScore = home.score !== undefined ? parseInt(home.score, 10) : null, aScore = away.score !== undefined ? parseInt(away.score, 10) : null;

  const hHT = (home.linescores && home.linescores.length > 0 && home.linescores[0].value !== undefined) ? parseInt(home.linescores[0].value, 10) : null;
  const aHT = (away.linescores && away.linescores.length > 0 && away.linescores[0].value !== undefined) ? parseInt(away.linescores[0].value, 10) : null;

  const hInfo = extractTeamStrength(home, true, hName);
  const aInfo = extractTeamStrength(away, false, aName);
  const lowData = !hInfo.hasData && !aInfo.hasData;

  const hBoost = hInfo.score;
  const aBoost = aInfo.score;
  const strengthDiff = hBoost - aBoost;

  const isDerby = hBoost >= 0.22 && aBoost >= 0.22 && Math.abs(strengthDiff) <= 0.18;

  const lgGoals = lg.gBase || 2.62;
  const homeAdvShare = strengthDiff < -0.35 ? 0.460 : (strengthDiff < -0.15 ? 0.490 : (strengthDiff > 0.25 ? 0.555 : 0.525));
  const baseH = lgGoals * homeAdvShare;
  const baseA = lgGoals * (1 - homeAdvShare);
  const paceMod = (0.26 - (hInfo.drawRatio + aInfo.drawRatio) / 2) * 0.45 + (hBoost + aBoost) * 0.16;

  let lamH = Math.max(0.40, Math.min(3.35, baseH + strengthDiff * 1.05 + paceMod * 0.50));
  let lamA = Math.max(0.40, Math.min(3.35, baseA - strengthDiff * 1.05 + paceMod * 0.50));

  const mkt = extractMarketOdds(comp);
  if (mkt && mkt.mktPH && mkt.mktPA && (mkt.mktPH + mkt.mktPA) > 0.2) {
    let targetTotal = lamH + lamA;
    if (mkt.ouLine && mkt.ouLine >= 1.5 && mkt.ouLine <= 4.0) {
      targetTotal = targetTotal * 0.60 + mkt.ouLine * 0.40;
    }
    const mktShareH = Math.max(0.15, Math.min(0.85, mkt.mktPH / (mkt.mktPH + mkt.mktPA)));
    const modShareH = lamH / (lamH + lamA);
    const finalShareH = modShareH * 0.45 + mktShareH * 0.55;
    lamH = Math.max(0.40, Math.min(3.35, targetTotal * finalShareH));
    lamA = Math.max(0.40, Math.min(3.35, targetTotal * (1 - finalShareH)));
  }

  const rho = (lg.rho || -0.09) + (isDerby ? -0.02 : 0);

  let pH = 0, pD = 0, pA = 0, p00 = 0, pO15 = 0, pO25 = 0, pU25 = 0, pGG = 0;
  let p1_O15 = 0, p2_O15 = 0, p1X_O15 = 0, pX2_O15 = 0, p1X_U35 = 0, pX2_U35 = 0;
  let totalProbMass = 0;

  for (let h = 0; h <= 7; h++) {
    for (let a = 0; a <= 7; a++) {
      const rawP = poissonPmf(h, lamH) * poissonPmf(a, lamA) * dixonColesTau(h, a, lamH, lamA, rho);
      totalProbMass += rawP;

      if (h === 0 && a === 0) p00 += rawP;
      if (h > a) pH += rawP;
      else if (h === a) pD += rawP;
      else pA += rawP;

      const goals = h + a;
      if (goals >= 2) pO15 += rawP;
      if (goals >= 3) pO25 += rawP;
      else pU25 += rawP;
      if (h > 0 && a > 0) pGG += rawP;

      if (h > a && goals >= 2) p1_O15 += rawP;
      if (a > h && goals >= 2) p2_O15 += rawP;
      if (h >= a && goals >= 2) p1X_O15 += rawP;
      if (a >= h && goals >= 2) pX2_O15 += rawP;
      if (h >= a && goals <= 3) p1X_U35 += rawP;
      if (a >= h && goals <= 3) pX2_U35 += rawP;
    }
  }

  pH /= totalProbMass; pD /= totalProbMass; pA /= totalProbMass; p00 /= totalProbMass;
  pO15 /= totalProbMass; pO25 /= totalProbMass; pU25 /= totalProbMass; pGG /= totalProbMass;
  p1_O15 /= totalProbMass; p2_O15 /= totalProbMass;
  p1X_O15 /= totalProbMass; pX2_O15 /= totalProbMass;
  p1X_U35 /= totalProbMass; pX2_U35 /= totalProbMass;

  const p1X = pH + pD;
  const pX2 = pA + pD;

  const nonZeroDraw = Math.max(0, pD - p00);
  const pPSF1 = Math.min(0.85, pH + nonZeroDraw * 0.34 + pA * 0.06);
  const pPSF2 = Math.min(0.83, pA + nonZeroDraw * 0.34 + pH * 0.06);

  const totalXG = lamH + lamA;
  const xgDiff = lamH - lamA;

  const candidates = [];

  const addCandidate = (name, mktType, prob, realOdd, specificityWeight) => {
    const fairOdd = 1 / Math.max(0.15, prob);
    const displayOdd = realOdd ? +realOdd.toFixed(2) : +(0.93 * fairOdd).toFixed(2);
    if (displayOdd < 1.33 || displayOdd > 2.35 || prob < 0.50) return;

    const edgePct = realOdd ? Math.round((prob * realOdd - 1) * 100) : 0;
    const edgeBonus = (realOdd && edgePct > 0) ? Math.min(0.08, edgePct * 0.008) : 0;
    const valueScore = prob * specificityWeight + edgeBonus;
    candidates.push({ name, mktType, prob, odd: displayOdd, edgePct, valueScore });
  };

  if (pH >= 0.48) addCandidate(`1 (${hName})`, "SOLO", pH, mkt?.decH, 1.10);
  if (pA >= 0.48) addCandidate(`2 (${aName})`, "SOLO", pA, mkt?.decA, 1.10);

  if (pH >= 0.62 && p1_O15 >= 0.53) addCandidate(`1 & Peste 1.5 Goluri`, "COMBO_SOLO", p1_O15, null, 1.07);
  if (pA >= 0.60 && p2_O15 >= 0.52) addCandidate(`2 & Peste 1.5 Goluri`, "COMBO_SOLO", p2_O15, null, 1.07);

  if (pO25 >= 0.53 && totalXG >= 2.62) addCandidate("Peste 2.5 Goluri", "O25", pO25, null, 1.06);
  if (pGG >= 0.54 && lamH >= 1.12 && lamA >= 1.02) addCandidate("GG (Ambele marchează)", "GG", pGG, null, 1.05);
  if (pU25 >= 0.56 && totalXG <= 2.26) addCandidate("Sub 2.5 Goluri", "U25", pU25, null, 1.04);

  if (xgDiff >= 0.18 && p1X_O15 >= 0.55 && totalXG >= 2.42) addCandidate("1X & Peste 1.5 Goluri", "COMBO_DC", p1X_O15, null, 1.04);
  if (xgDiff <= -0.18 && pX2_O15 >= 0.54 && totalXG >= 2.42) addCandidate("X2 & Peste 1.5 Goluri", "COMBO_DC", pX2_O15, null, 1.04);
  if (xgDiff >= 0.14 && p1X_U35 >= 0.57 && totalXG <= 2.50) addCandidate("1X & Sub 3.5 Goluri", "COMBO_U35", p1X_U35, null, 1.01);
  if (xgDiff <= -0.14 && pX2_U35 >= 0.57 && totalXG <= 2.50) addCandidate("X2 & Sub 3.5 Goluri", "COMBO_U35", pX2_U35, null, 1.01);

  if (pH >= 0.42 && pH <= 0.52 && xgDiff >= 0.15) addCandidate(`PSF 1 (${hName})`, "PSF", pPSF1, null, 0.99);
  if (pA >= 0.42 && pA <= 0.52 && xgDiff <= -0.15) addCandidate(`PSF 2 (${aName})`, "PSF", pPSF2, null, 0.99);

  if (pO15 >= 0.62 && pO15 <= 0.69) addCandidate("Peste 1.5 Goluri", "O15", pO15, null, 0.94);
  if (xgDiff >= 0.12 && p1X >= 0.58 && p1X <= 0.69) addCandidate("Șansă Dublă 1X", "DC", p1X, null, 0.92);
  if (xgDiff <= -0.12 && pX2 >= 0.58 && pX2 <= 0.69) addCandidate("Șansă Dublă X2", "DC", pX2, null, 0.92);

  if (!candidates.length) {
    if (pH >= pA && pH >= 0.44) candidates.push({ name: `1 (${hName})`, mktType: "SOLO", prob: pH, odd: +(0.93 / pH).toFixed(2), edgePct: 0, valueScore: pH });
    else if (pA > pH && pA >= 0.44) candidates.push({ name: `2 (${aName})`, mktType: "SOLO", prob: pA, odd: +(0.93 / pA).toFixed(2), edgePct: 0, valueScore: pA });
    else if (xgDiff < 0) candidates.push({ name: "Șansă Dublă X2", mktType: "DC", prob: pX2, odd: Math.max(1.25, +(0.92 / pX2).toFixed(2)), edgePct: 0, valueScore: pX2 * 0.9 });
    else candidates.push({ name: "Șansă Dublă 1X", mktType: "DC", prob: p1X, odd: Math.max(1.25, +(0.92 / p1X).toFixed(2)), edgePct: 0, valueScore: p1X * 0.9 });
  }

  candidates.sort((a, b) => b.valueScore - a.valueScore);
  const best = candidates[0];

  const getStat = (compObj, names) => {
    if (!compObj.statistics) return null;
    for (let n of names) {
      const f = compObj.statistics.find(s => s.name === n || s.abbreviation === n);
      if (f && f.displayValue !== undefined) {
        const val = parseFloat(f.displayValue);
        if (!isNaN(val)) return val;
      }
    }
    return null;
  };

  const realHCorners = getStat(home, ["wonCorners", "cornerKicks", "corners", "CK"]);
  const realACorners = getStat(away, ["wonCorners", "cornerKicks", "corners", "CK"]);
  const realHYellow = getStat(home, ["yellowCards", "YC"]);
  const realAYellow = getStat(away, ["yellowCards", "YC"]);
  const realHRed = getStat(home, ["redCards", "RC"]) || 0;
  const realARed = getStat(away, ["redCards", "RC"]) || 0;

  const offensiveMomentum = ((hInfo.winsCount + aInfo.winsCount) - 3.8) * 0.28;
  const openPlayFactor = (0.26 - (hInfo.drawRatio + aInfo.drawRatio) / 2) * 2.4;
  const mismatchPressure = Math.abs(lamH - lamA) * 0.65;
  const derbyCornerPush = isDerby ? 0.50 : 0;

  const expCornersNum = Math.max(7.2, Math.min(12.6, 
    (lg.cBase || 9.5) + (totalXG - (lg.gBase || 2.62)) * 1.45 + mismatchPressure + offensiveMomentum + openPlayFactor + derbyCornerPush
  ));
  const expCorners = expCornersNum.toFixed(1);
  const bestCornerOpt = selectOptimalStatLine(expCornersNum, [7.5, 8.5, 9.5], [9.5, 10.5]);
  const cornerLine = `${bestCornerOpt.label} (${bestCornerOpt.prob}%)`;

  const closeness = 1 - Math.min(1, Math.abs(pH - pA) * 1.75);
  const frustrationFactor = ((hInfo.lossesCount + aInfo.lossesCount) - 2.8) * 0.24;
  const drawFriction = ((hInfo.drawRatio + aInfo.drawRatio) / 2 - 0.25) * 1.8;
  const derbyCardPush = isDerby ? 0.70 : 0;

  const expCardsNum = Math.max(2.6, Math.min(6.4, 
    (lg.kBase || 4.3) + (closeness - 0.52) * 1.20 + frustrationFactor + drawFriction + derbyCardPush
  ));
  const expCards = expCardsNum.toFixed(1);
  const bestCardOpt = selectOptimalStatLine(expCardsNum, [3.5, 4.5], [4.5, 5.5]);
  const cardLine = `${bestCardOpt.label} (${bestCardOpt.prob}%)`;

  const actualCorners = (realHCorners !== null && realACorners !== null) ? (realHCorners + realACorners) : null;
  const actualCards = (realHYellow !== null && realAYellow !== null) ? (realHYellow + realAYellow + realHRed + realARed) : null;

  return {
    id: ev.id, league: lg.name, icon: lg.icon, cat: lg.cat, date: roDateStr(dt), time: roTimeStr(dt),
    status: stState === "post" ? "FT" : (stState === "in" ? "LIVE" : "NS"),
    home: hName, away: aName, hScore, aScore, hHT, aHT, hForm: hInfo.formDisplay, aForm: aInfo.formDisplay,
    lamH: lamH.toFixed(2), lamA: lamA.toFixed(2),
    isDerby, lowData, hasMktOdds: !!(mkt && (mkt.mktPH || mkt.ouLine)),
    edgePct: best.edgePct || 0,
    pick: best.name, mktType: best.mktType || "OTHER", prob: Math.round(best.prob * 100), odd: +best.odd.toFixed(2),
    tipsterScore: best.valueScore * (lowData ? 0.82 : 1.0),
    expCorners, cornerLine, actualCorners,
    expCards, cardLine, actualCards,
    probs: { p1: Math.round(pH*100), pX: Math.round(pD*100), p2: Math.round(pA*100), o25: Math.round(pO25*100), gg: Math.round(pGG*100), o15: Math.round(pO15*100) }
  };
}

function buildOptimalTicket(pool, targetOdd) {
  if (!pool || !pool.length) return { picks: [], totalOdd: 1.0 };
  const sorted = [...pool].sort((a, b) => b.tipsterScore - a.tipsterScore);
  const picks = [];
  const usedIds = new Set();
  const marketCounts = {};
  let tot = 1.0;

  while (picks.length < 11 && tot < targetOdd * 0.94) {
    const remainingNeeded = targetOdd / tot;
    let bestCandidate = null;
    let bestScore = -999;

    for (let m of sorted) {
      if (usedIds.has(m.id)) continue;
      const mCount = marketCounts[m.mktType] || 0;
      const diversityPenalty = mCount >= 2 ? 0.78 : (mCount === 1 ? 0.92 : 1.05);

      let targetFit = 1.0;
      if (remainingNeeded <= 2.25) {
        const dist = Math.abs(m.odd - remainingNeeded);
        targetFit = Math.max(0.5, 1.35 - dist * 0.65);
      }

      const candidateScore = m.tipsterScore * diversityPenalty * targetFit;
      if (candidateScore > bestScore) {
        bestScore = candidateScore;
        bestCandidate = m;
      }
    }

    if (!bestCandidate) break;
    picks.push(bestCandidate);
    usedIds.add(bestCandidate.id);
    marketCounts[bestCandidate.mktType] = (marketCounts[bestCandidate.mktType] || 0) + 1;
    tot *= bestCandidate.odd;
  }

  return { picks, totalOdd: tot };
}

async function fetchWithTimeout(url, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timer);
    return await res.json();
  } catch (e) {
    clearTimeout(timer);
    throw e;
  }
}

async function loadMatchesForDate(iso) {
  renderSubBars();
  if (cacheByDate[iso]) { renderViewport(); return; }
  document.getElementById("viewport").innerHTML = `<div class="cyber-card" style="text-align:center;padding:28px;color:var(--neon-cyan);">⚡ Joe scanează clasamentele și datele xG pentru <b>${iso}</b>...</div>`;
  const ymd = iso.replace(/-/g, "");
  const res = await Promise.all(LEAGUES.map(l =>
    fetchWithTimeout(`https://site.api.espn.com/apis/site/v2/sports/soccer/${l.slug}/scoreboard?dates=${ymd}`)
      .then(d => ({ l, evs: (d && d.events) || [] }))
      .catch(() => ({ l, evs: [] }))
  ));
  const list = [];
  res.forEach(r => r.evs.forEach(ev => {
    try {
      const m = analyzeMatch(ev, r.l);
      if (m.date === iso) list.push(m);
    } catch (e) {}
  }));

  if (list.length > 0) {
    cacheByDate[iso] = list;
    try { localStorage.setItem("joe_v7_cache_" + iso, JSON.stringify(list)); } catch (e) {}
  } else {
    try {
      const backup = localStorage.getItem("joe_v7_cache_" + iso);
      cacheByDate[iso] = backup ? JSON.parse(backup) : [];
    } catch (e) { cacheByDate[iso] = []; }
  }

  autoSettleProjectBets(cacheByDate[iso]);
  renderViewport();
}

async function loadEuropaMatches() {
  renderSubBars();
  if (europaMatches.length) { renderViewport(); return; }
  document.getElementById("viewport").innerHTML = `<div class="cyber-card" style="text-align:center;padding:28px;color:var(--neon-gold);">🏆 Joe analizează cupele europene...</div>`;
  const now = new Date(), s = roDateStr(new Date(now.getTime() - 2*86400000)).replace(/-/g, ""), e = roDateStr(new Date(now.getTime() + 18*86400000)).replace(/-/g, "");
  const res = await Promise.all(LEAGUES.filter(l => l.cat === "eu").map(l =>
    fetchWithTimeout(`https://site.api.espn.com/apis/site/v2/sports/soccer/${l.slug}/scoreboard?dates=${s}-${e}`)
      .then(d => ({ l, evs: (d && d.events) || [] }))
      .catch(() => ({ l, evs: [] }))
  ));
  const list = [];
  res.forEach(r => r.evs.forEach(ev => {
    try { list.push(analyzeMatch(ev, r.l)); } catch (err) {}
  }));
  list.sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
  europaMatches = list;
  renderViewport();
}

async function initProject() {
  if (isSupabaseConfigured()) {
    try {
      const r = await fetch(`${SUPABASE_URL}/rest/v1/jack_project?id=eq.1&select=data`, { headers: sbHeaders() });
      if (r.ok) {
        const rows = await r.json();
        if (rows && rows.length > 0 && rows[0].data) project = rows[0].data;
      }
    } catch (e) { console.error(e); }
  }
  recalcBankroll(false);
}

async function saveToDB() {
  if (!isSupabaseConfigured()) return;
  try {
    const r = await fetch(`${SUPABASE_URL}/rest/v1/jack_project?id=eq.1`, {
      method: "PATCH",
      headers: sbHeaders(),
      body: JSON.stringify({ data: project })
    });
    document.getElementById("liveClock").innerText = r.ok ? "● Cloud Synced" : "● Sync Error";
  } catch (e) {
    document.getElementById("liveClock").innerText = "● Sync Error";
  }
}

function recalcBankroll(shouldSave = true) {
  let b = project.initial_bankroll || 500.0;
  (project.bets || []).forEach(bet => {
    if (bet.status === "WIN") b += bet.stake * (bet.odd - 1);
    else if (bet.status === "LOSS") b -= bet.stake;
  });
  project.bankroll = +b.toFixed(2);
  document.getElementById("topBankroll").innerText = project.bankroll.toFixed(2);
  if (shouldSave) saveToDB();
}

function checkBetOutcome(pick, h, a, hHT = null, aHT = null) {
  const t = h + a;
  if (pick.startsWith("1 (")) return h > a;
  if (pick.startsWith("2 (")) return a > h;
  if (pick === "1 & Peste 1.5 Goluri") return h > a && t >= 2;
  if (pick === "2 & Peste 1.5 Goluri") return a > h && t >= 2;
  if (pick.startsWith("PSF 1")) return h > a || (hHT !== null && aHT !== null && hHT > aHT);
  if (pick.startsWith("PSF 2")) return a > h || (hHT !== null && aHT !== null && aHT > hHT);
  if (pick.includes("1X & Peste 1.5")) return h >= a && t >= 2;
  if (pick.includes("X2 & Peste 1.5")) return a >= h && t >= 2;
  if (pick.includes("1X & Sub 3.5")) return h >= a && t <= 3;
  if (pick.includes("X2 & Sub 3.5")) return a >= h && t <= 3;
  if (pick.includes("Peste 2.5")) return t >= 3;
  if (pick.includes("Sub 2.5")) return t <= 2;
  if (pick.includes("Peste 1.5")) return t >= 2;
  if (pick.includes("GG")) return h > 0 && a > 0;
  if (pick.includes("1X")) return h >= a;
  if (pick.includes("X2")) return a >= h;
  return null;
}

function autoSettleProjectBets(list) {
  let ch = false;
  (project.bets || []).forEach(b => {
    if (b.status !== "PENDING") return;
    const f = list.find(m => String(m.id) === String(b.matchId) && m.status === "FT");
    if (f && f.hScore !== null) {
      const w = checkBetOutcome(b.pick, f.hScore, f.aScore, f.hHT, f.aHT);
      if (w !== null) { b.status = w ? "WIN" : "LOSS"; b.score = `${f.hScore}-${f.aScore}`; ch = true; }
    }
  });
  if (ch) recalcBankroll(true);
}

function addMatchToProject(matchId) {
  if (!hasJoeAccess()) return;
  const all = [...(cacheByDate[selectedDate] || []), ...europaMatches];
  const m = all.find(x => String(x.id) === String(matchId));
  if (!m) return;
  if (!project.bets.some(b => String(b.matchId) === String(m.id))) {
    const smart = calculateSmartStake(project.bankroll, m);
    project.bets.unshift({ id: Date.now(), matchId: m.id, date: m.date, match: `${m.home} vs ${m.away}`, league: m.league, pick: m.pick, odd: m.odd, stake: smart.stake, status: "PENDING", score: "" });
    recalcBankroll(true);
  }
  switchNav("proiect");
}

function copyMatchById(matchId) {
  const all = [...(cacheByDate[selectedDate] || []), ...europaMatches];
  const m = all.find(x => String(x.id) === String(matchId));
  if (!m) return;
  copyText(`${m.home} vs ${m.away} — ${m.pick} (@${m.odd.toFixed(2)})`);
}

function editBetDetails(id) {
  const b = project.bets.find(x => x.id === id);
  if (!b) return;
  const o = parseFloat(prompt(`Cotă nouă pentru ${b.match}:`, b.odd));
  if (isNaN(o) || o <= 1.01) return;
  const s = parseFloat(prompt("Miză nouă (RON):", b.stake));
  if (isNaN(s) || s <= 0) return;
  b.odd = +o.toFixed(2); b.stake = +s.toFixed(2);
  recalcBankroll(true); renderViewport();
}

function updateBetStatus(id, st) {
  const b = project.bets.find(x => x.id === id);
  if (b) { b.status = st; recalcBankroll(true); renderViewport(); }
}

function deleteBet(id) {
  if (!confirm("Ștergi acest pariu?")) return;
  project.bets = project.bets.filter(x => x.id !== id);
  recalcBankroll(true); renderViewport();
}

function toggleDrawer(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = el.style.display === "block" ? "none" : "block";
}

// ================= INIȚIALIZARE APLICAȚIE =================
async function startApp() {
  selectedDate = getDatesList()[1].iso;
  const savedUser = localStorage.getItem("xmts_logged_user");
  const savedAdmToken = sessionStorage.getItem("xmts_adm_token");
  if (savedUser) {
    try {
      const parsed = JSON.parse(savedUser);
      const isExpired = parsed.role !== "admin" && parsed.expires_at && new Date(parsed.expires_at) < new Date();
      if (!isExpired && parsed.username) {
        currentUser = parsed;
        if (parsed.role === "admin" && savedAdmToken) {
          adminSessionPass = savedAdmToken;
          await fetchAdminUsersList();
        }
        document.getElementById("loginScreen").style.display = "none";
        applyRolePermissions();
      } else {
        localStorage.removeItem("xmts_logged_user");
      }
    } catch (e) {}
  }
  loadMatchesForDate(selectedDate);
  await initProject();
}

startApp();
