// ================= PARTEA 2: RATINGURI REALE CLUBURI + MOTOR ANALIZĂ CALIBRAT PE COTE =================

// Indice Power Rating (Elo + Valoare Lot): + pentru forțe, - pentru echipe din subsol/retrogradare
const CLUB_POWER = [
  // Elite & Top Champions League
  {k:"manchester city",p:0.55},{k:"real madrid",p:0.55},{k:"bayern",p:0.54},{k:"barcelona",p:0.52},
  {k:"liverpool",p:0.50},{k:"inter",p:0.48},{k:"arsenal",p:0.48},{k:"paris saint-germain",p:0.48},{k:"psg",p:0.48},
  {k:"leverkusen",p:0.42},{k:"napoli",p:0.44},{k:"atletico",p:0.40},{k:"atlético",p:0.40},{k:"dortmund",p:0.38},
  {k:"juventus",p:0.38},{k:"milan",p:0.36},{k:"atalanta",p:0.39},{k:"chelsea",p:0.36},{k:"tottenham",p:0.32},
  {k:"aston villa",p:0.31},{k:"newcastle",p:0.30},{k:"manchester united",p:0.26},{k:"leipzig",p:0.34},
  {k:"sporting",p:0.44},{k:"benfica",p:0.42},{k:"porto",p:0.40},{k:"psv",p:0.44},{k:"feyenoord",p:0.34},{k:"ajax",p:0.32},
  {k:"galatasaray",p:0.42},{k:"fenerbahce",p:0.40},{k:"fenerbahçe",p:0.40},{k:"besiktas",p:0.28},
  {k:"olympiacos",p:0.34},{k:"paok",p:0.31},{k:"panathinaikos",p:0.29},{k:"aek",p:0.29},
  // Echipe bune / Europa League
  {k:"lazio",p:0.30},{k:"roma",p:0.29},{k:"fiorentina",p:0.27},{k:"bologna",p:0.20},{k:"torino",p:0.12},
  {k:"athletic",p:0.28},{k:"villarreal",p:0.27},{k:"real sociedad",p:0.24},{k:"betis",p:0.22},{k:"girona",p:0.18},
  {k:"frankfurt",p:0.27},{k:"stuttgart",p:0.27},{k:"monaco",p:0.32},{k:"marseille",p:0.31},{k:"lille",p:0.28},{k:"lyon",p:0.25},
  {k:"brighton",p:0.22},{k:"fulham",p:0.15},{k:"bournemouth",p:0.14},{k:"west ham",p:0.14},{k:"braga",p:0.25},
  // SuperLiga României (Top vs Subsol)
  {k:"fcsb",p:0.32},{k:"cfr cluj",p:0.28},{k:"universitatea craiova",p:0.26},{k:"craiova",p:0.26},
  {k:"universitatea cluj",p:0.22},{k:"u cluj",p:0.22},{k:"rapid",p:0.22},{k:"dinamo",p:0.16},{k:"sepsi",p:0.12},{k:"farul",p:0.10},
  {k:"slobozia",p:-0.24},{k:"botoșani",p:-0.20},{k:"botosani",p:-0.20},{k:"buzău",p:-0.25},{k:"buzau",p:-0.25},{k:"poli iași",p:-0.18},{k:"ermannstadt",p:-0.10},
  // Echipe mici / Subsol Serie A, La Liga, Premier League, Ligue 1, Bundesliga (Previne eroarea Monza vs Napoli!)
  {k:"monza",p:-0.24},{k:"lecce",p:-0.26},{k:"venezia",p:-0.28},{k:"empoli",p:-0.20},{k:"cagliari",p:-0.20},
  {k:"verona",p:-0.22},{k:"parma",p:-0.16},{k:"como",p:-0.14},{k:"genoa",p:-0.16},{k:"udinese",p:-0.06},{k:"sassuolo",p:-0.12},
  {k:"valladolid",p:-0.28},{k:"las palmas",p:-0.24},{k:"leganes",p:-0.22},{k:"espanyol",p:-0.22},{k:"getafe",p:-0.14},{k:"alaves",p:-0.18},
  {k:"southampton",p:-0.30},{k:"ipswich",p:-0.28},{k:"leicester",p:-0.24},{k:"wolves",p:-0.18},{k:"everton",p:-0.14},{k:"crystal palace",p:-0.08},
  {k:"kiel",p:-0.28},{k:"bochum",p:-0.28},{k:"st. pauli",p:-0.24},{k:"heidenheim",p:-0.20},{k:"augsburg",p:-0.14},
  {k:"le havre",p:-0.26},{k:"angers",p:-0.26},{k:"montpellier",p:-0.24},{k:"saint-etienne",p:-0.22},{k:"nantes",p:-0.18},{k:"auxerre",p:-0.16}
];

function getClubBasePower(name) {
  const low = (name || "").toLowerCase();
  for (let c of CLUB_POWER) if (low.includes(c.k)) return c.p;
  return 0;
}

// Suprascriem extractTeamStrength pentru a combina Clasamentul la zi (fără comprimare excesivă) cu Power Rating-ul clubului
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
      // Multiplicator puternic (0.62) pe PPG ca diferența dintre 2.2 PPG și 0.8 PPG să fie majoră
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

  // Combinăm performanța din sezonul curent cu valoarea structurală a clubului (Power Rating)
  let totalStrength = statsStrength;
  if (clubPower !== 0 && (hasRealRecord || hasRealForm)) {
    totalStrength = statsStrength * 0.55 + clubPower * 0.65;
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
  const strengthDiff = hBoost - aBoost; // Ex: Monza (-0.28) vs Napoli (+0.44) => strengthDiff = -0.72!

  const isDerby = hBoost >= 0.22 && aBoost >= 0.22 && Math.abs(strengthDiff) <= 0.18;

  // Avantajul terenului propriu scade când oaspeții sunt mult mai valoroși decât gazdele
  const lgGoals = lg.gBase || 2.62;
  const homeAdvShare = strengthDiff < -0.25 ? 0.510 : (strengthDiff > 0.25 ? 0.555 : 0.535);
  const baseH = lgGoals * homeAdvShare;
  const baseA = lgGoals * (1 - homeAdvShare);
  const paceMod = (0.26 - (hInfo.drawRatio + aInfo.drawRatio) / 2) * 0.45 + (hBoost + aBoost) * 0.16;

  let lamH = Math.max(0.45, Math.min(3.35, baseH + strengthDiff * 0.98 + paceMod * 0.50));
  let lamA = Math.max(0.38, Math.min(3.10, baseA - strengthDiff * 0.88 + paceMod * 0.50));

  // Dacă ESPN trimite cotele reale ale caselor de pariuri, calibrăm xG-ul cu piața
  const mkt = extractMarketOdds(comp);
  if (mkt && mkt.mktPH && mkt.mktPA && (mkt.mktPH + mkt.mktPA) > 0.2) {
    let targetTotal = lamH + lamA;
    if (mkt.ouLine && mkt.ouLine >= 1.5 && mkt.ouLine <= 4.0) {
      targetTotal = targetTotal * 0.65 + mkt.ouLine * 0.35;
    }
    const mktShareH = Math.max(0.20, Math.min(0.80, mkt.mktPH / (mkt.mktPH + mkt.mktPA)));
    const modShareH = lamH / (lamH + lamA);
    const finalShareH = modShareH * 0.55 + mktShareH * 0.45;
    lamH = Math.max(0.45, Math.min(3.35, targetTotal * finalShareH));
    lamA = Math.max(0.38, Math.min(3.10, targetTotal * (1 - finalShareH)));
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

  // 1. Soliști (1 / 2)
  if (pH >= 0.48) addCandidate(`1 (${hName})`, "SOLO", pH, mkt?.decH, 1.10);
  if (pA >= 0.48) addCandidate(`2 (${aName})`, "SOLO", pA, mkt?.decA, 1.10);

  // 2. Solist & Peste 1.5 Goluri
  if (pH >= 0.62 && p1_O15 >= 0.53) addCandidate(`1 & Peste 1.5 Goluri`, "COMBO_SOLO", p1_O15, null, 1.07);
  if (pA >= 0.60 && p2_O15 >= 0.52) addCandidate(`2 & Peste 1.5 Goluri`, "COMBO_SOLO", p2_O15, null, 1.07);

  // 3. Piețe de goluri
  if (pO25 >= 0.53 && totalXG >= 2.62) addCandidate("Peste 2.5 Goluri", "O25", pO25, null, 1.06);
  if (pGG >= 0.54 && lamH >= 1.12 && lamA >= 1.02) addCandidate("GG (Ambele marchează)", "GG", pGG, null, 1.05);
  if (pU25 >= 0.56 && totalXG <= 2.26) addCandidate("Sub 2.5 Goluri", "U25", pU25, null, 1.04);

  // 4. Combo Șansă Dublă & Goluri (strict în direcția echipei favorite!)
  if (xgDiff >= 0.18 && p1X_O15 >= 0.55 && totalXG >= 2.42) addCandidate("1X & Peste 1.5 Goluri", "COMBO_DC", p1X_O15, null, 1.04);
  if (xgDiff <= -0.18 && pX2_O15 >= 0.54 && totalXG >= 2.42) addCandidate("X2 & Peste 1.5 Goluri", "COMBO_DC", pX2_O15, null, 1.04);
  if (xgDiff >= 0.14 && p1X_U35 >= 0.57 && totalXG <= 2.50) addCandidate("1X & Sub 3.5 Goluri", "COMBO_U35", p1X_U35, null, 1.01);
  if (xgDiff <= -0.14 && pX2_U35 >= 0.57 && totalXG <= 2.50) addCandidate("X2 & Sub 3.5 Goluri", "COMBO_U35", pX2_U35, null, 1.01);

  // 5. Pauză sau Final (PSF 1 / PSF 2)
  if (pH >= 0.42 && pH <= 0.52 && xgDiff >= 0.15) addCandidate(`PSF 1 (${hName})`, "PSF", pPSF1, null, 0.99);
  if (pA >= 0.42 && pA <= 0.52 && xgDiff <= -0.15) addCandidate(`PSF 2 (${aName})`, "PSF", pPSF2, null, 0.99);

  // 6. Peste 1.5 Goluri / 1X / X2 (Interzis 1X dacă oaspeții sunt mai buni!)
  if (pO15 >= 0.62 && pO15 <= 0.69) addCandidate("Peste 1.5 Goluri", "O15", pO15, null, 0.94);
  if (xgDiff >= 0.10 && p1X >= 0.58 && p1X <= 0.69) addCandidate("Șansă Dublă 1X", "DC", p1X, null, 0.92);
  if (xgDiff <= -0.10 && pX2 >= 0.58 && pX2 <= 0.69) addCandidate("Șansă Dublă X2", "DC", pX2, null, 0.92);

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
    try { localStorage.setItem("joe_v5_cache_" + iso, JSON.stringify(list)); } catch (e) {}
  } else {
    try {
      const backup = localStorage.getItem("joe_v5_cache_" + iso);
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

function getMatchesContextString() {
  const dayList = cacheByDate[selectedDate] || [];
  if (!dayList.length) return "";
  return dayList.slice(0, 18).map(m => 
    `${m.home} vs ${m.away} (${m.league}): Pont=${m.pick} @${m.odd} (${m.prob}%), xG=${m.lamH}-${m.lamA}, Cornere=${m.cornerLine} (~${m.expCorners}), Cartonase=${m.cardLine} (~${m.expCards})`
  ).join("\n");
}

function compressImageFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = e => {
      const img = new Image();
      img.onload = () => {
        const MAX_DIM = 1100;
        let w = img.width, h = img.height;
        if (w > MAX_DIM || h > MAX_DIM) {
          if (w > h) { h = Math.round(h * (MAX_DIM / w)); w = MAX_DIM; }
          else { w = Math.round(w * (MAX_DIM / h)); h = MAX_DIM; }
        }
        const canvas = document.createElement("canvas");
        canvas.width = w; canvas.height = h;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, w, h);
        const dataUrl = canvas.toDataURL("image/jpeg", 0.82);
        resolve({ base64: dataUrl, mimeType: "image/jpeg" });
      };
      img.onerror = () => resolve({ base64: e.target.result, mimeType: file.type || "image/jpeg" });
      img.src = e.target.result;
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function sendToJoeBackend(promptText, imageObj = null) {
  const loadingId = Date.now() + Math.random();
  vipChatMessages.push({ 
    sender: 'joe', 
    text: imageObj ? "🔎 Joe scanează imaginea..." : "⚡ Joe analizează...", 
    id: loadingId 
  });
  updateChatUI();

  try {
    const payload = {
      prompt: promptText,
      matchesContext: getMatchesContextString()
    };

    if (imageObj && imageObj.base64) {
      payload.imageBase64 = imageObj.base64;
      payload.mimeType = imageObj.mimeType || "image/jpeg";
    }

    const response = await fetch(`${SUPABASE_URL}/functions/v1/joe-chat`, {
      method: "POST",
      headers: {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const data = await response.json();
    const aiReply = data.reply || "Băiatu', serverul neural n-a returnat niciun răspuns. Mai încearcă o dată!";

    vipChatMessages = vipChatMessages.filter(m => m.id !== loadingId);
    vipChatMessages.push({ sender: 'joe', text: aiReply });
  } catch (err) {
    vipChatMessages = vipChatMessages.filter(m => m.id !== loadingId);
    vipChatMessages.push({ sender: 'joe', text: "Eroare de conexiune cu Supabase, șefu'!" });
  }

  updateChatUI();
}

async function handleVipChatSubmit(event) {
  event.preventDefault();
  const input = document.getElementById("vipChatInput");
  const txt = (input?.value || "").trim();
  if (!txt) return;

  vipChatMessages.push({ sender: 'user', text: txt });
  input.value = "";
  updateChatUI();

  await sendToJoeBackend(txt, lastUploadedImage);
}

async function handleImageUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const input = document.getElementById("vipChatInput");
  const customQuestion = (input?.value || "").trim();
  if (input) input.value = "";

  try {
    const compressed = await compressImageFile(file);
    lastUploadedImage = compressed;

    const camBtn = document.getElementById("chatCamBtn");
    if (camBtn) camBtn.classList.add("has-img");

    vipChatMessages.push({ 
      sender: 'user', 
      text: customQuestion || '📷 Analizează această imagine scurt și la obiect:', 
      img: compressed.base64 
    });
    updateChatUI();

    await sendToJoeBackend(
      customQuestion || "Analizează această imagine (bilet sau statistici) scurt și la obiect și dă-mi verdictul tău!",
      compressed
    );
  } catch (e) {
    vipChatMessages.push({ sender: 'joe', text: "Nu am putut citi fișierul imagine, șefu'. Încearcă altă captură!" });
    updateChatUI();
  } finally {
    event.target.value = "";
  }
}

function updateChatUI() {
  const box = document.getElementById("chatMessagesBox");
  if(!box) return;
  box.innerHTML = vipChatMessages.map(m => {
    let imgHtml = m.img ? `<br><img src="${m.img}" class="preview-thumb">` : '';
    return `<div class="chat-msg ${m.sender}">${m.sender === 'joe' ? '🤖 <b>Joe:</b> ' : '👤 <b>Tu:</b> '}${m.text}${imgHtml}</div>`;
  }).join("");
  box.scrollTop = box.scrollHeight;
}

function selectTicketOdd(odd) {
  if (isGeneratingTicket) return;
  targetTicketOdds = odd;
  isGeneratingTicket = true;
  renderViewport();

  setTimeout(() => {
    const stEl = document.getElementById("neuralStepText");
    if (stEl) stEl.innerText = "🧠 Rulare model Poisson + Dixon-Coles...";
  }, 360);

  setTimeout(() => {
    const stEl = document.getElementById("neuralStepText");
    if (stEl) stEl.innerText = "🎯 Optimizare combinatorială cotă ~" + odd + "...";
  }, 720);

  setTimeout(() => {
    isGeneratingTicket = false;
    renderViewport();
  }, 1100);
}

function renderSubBars() {
  const sb = document.getElementById("subBars");
  const searchBox = document.getElementById("searchContainer");
  
  if (currentNav === "admin") { 
    sb.style.display = "none"; 
    searchBox.style.display = "none";
    return; 
  }
  
  if (currentNav === "meciuri" || currentNav === "europa") {
    searchBox.style.display = "block";
  } else {
    searchBox.style.display = "none";
  }

  const dates = getDatesList();
  if (!selectedDate) selectedDate = dates[1].iso;
  const dBar = document.getElementById("dateBar"), lBar = document.getElementById("leagueBar");
  
  if (currentNav === "europa") {
    sb.style.display = "block";
    dBar.innerHTML = `<span style="font-size:11px;color:var(--neon-gold);font-weight:800;font-family:'Orbitron',sans-serif;">🏆 SECTOR UEFA EUROPEAN</span>`;
    lBar.innerHTML = ""; return;
  }
  
  sb.style.display = "block";
  dBar.innerHTML = dates.map(d => `<button class="cyber-chip ${selectedDate===d.iso?'active':''}" onclick="selectDay('${d.iso}')">${d.label}</button>`).join("");
  if (currentNav === "proiect" || currentNav === "bilete") { lBar.innerHTML = ""; return; }
  const dayList = cacheByDate[selectedDate] || [], lgs = [...new Set(dayList.map(m => m.league))];
  lBar.innerHTML = `<button class="cyber-chip cyber-chip-gold ${selectedLeague==='ALL'?'active':''}" onclick="selectLeague('ALL')">Toate (${dayList.length})</button>` +
    lgs.map(lg => `<button class="cyber-chip cyber-chip-gold ${selectedLeague===lg?'active':''}" onclick="selectLeague('${lg}')">${lg} (${dayList.filter(m=>m.league===lg).length})</button>`).join("");
}

function renderMatchCard(m) {
  const stClass = m.status === "FT" ? "st-ft" : (m.status === "LIVE" ? "st-live" : "st-ns");
  
  let cardStatusClass = "";
  if (m.status === "FT" && m.hScore !== null && m.aScore !== null) {
    const outcome = checkBetOutcome(m.pick, m.hScore, m.aScore, m.hHT, m.aHT);
    if (outcome === true) cardStatusClass = "match-win";
    else if (outcome === false) cardStatusClass = "match-loss";
  }

  const stText = m.status === "FT" ? `FT (${m.hScore}-${m.aScore})` : (m.status === "LIVE" ? `LIVE ${m.hScore}-${m.aScore}` : `🕒 ${m.time}`);
  const center = (m.status === "FT" || m.status === "LIVE") ? `${m.hScore} - ${m.aScore}` : "VS";
  const joeBtnHtml = hasJoeAccess() ? `<button class="cyber-btn accent" onclick="addMatchToProject('${m.id}')">➕ La Joe</button>` : "";

  const derbyBadge = m.isDerby ? ` · <span style="color:var(--neon-gold);font-weight:800;">🔥 DERBY</span>` : "";
  const lowDataBadge = m.lowData ? ` · <span style="color:var(--neon-red);">⚠️ Istoric limitat</span>` : "";
  const edgeBadge = (m.edgePct && m.edgePct > 0) ? ` · <span style="color:var(--neon-cyan);">📡 +${m.edgePct}% EV</span>` : "";

  const cornersDisplay = m.actualCorners !== null 
    ? `<b style="color:var(--neon-cyan);">${m.actualCorners} în meci</b> (Linie: ${m.cornerLine} · Est: ${m.expCorners})` 
    : `<b style="color:var(--neon-cyan);">${m.cornerLine}</b> (Medie est: ~${m.expCorners})`;
  const cardsDisplay = m.actualCards !== null 
    ? `<b style="color:var(--neon-gold);">${m.actualCards} în meci</b> (Linie: ${m.cardLine} · Est: ${m.expCards})` 
    : `<b style="color:var(--neon-gold);">${m.cardLine}</b> (Medie est: ~${m.expCards})`;

  return `<div class="cyber-card ${cardStatusClass}">
    <div class="card-top"><span>${m.icon} ${m.league} · ${m.date}${derbyBadge}${lowDataBadge}</span><span class="status-badge ${stClass}">${stText}</span></div>
    <div class="teams-container"><div class="team-name">${m.home}</div><div class="score-display">${center}</div><div class="team-name away">${m.away}</div></div>
    <div class="prediction-panel"><div><div class="pred-main">⭐ ${m.pick}</div><div class="pred-sub">Siguranță: <b style="color:var(--neon-green);">${m.prob}%</b> · xG: ${m.lamH}-${m.lamA}${edgeBadge}</div></div><div class="odd-chip">@${m.odd.toFixed(2)}</div></div>
    <div class="action-bar">
      <button class="cyber-btn" onclick="toggleDrawer('dr-${m.id}')">📊 Analiză</button>
      <button class="cyber-btn copy-btn" onclick="copyMatchById('${m.id}')">📋 Copiază</button>
      ${joeBtnHtml}
    </div>
    <div class="analytics-drawer" id="dr-${m.id}">
      <div class="matrix-grid">
        <div class="matrix-cell">1<b>${m.probs.p1}%</b></div><div class="matrix-cell">X<b>${m.probs.pX}%</b></div><div class="matrix-cell">2<b>${m.probs.p2}%</b></div>
        <div class="matrix-cell">Peste 1.5<b>${m.probs.o15}%</b></div><div class="matrix-cell">Peste 2.5<b>${m.probs.o25}%</b></div><div class="matrix-cell">GG<b>${m.probs.gg}%</b></div>
      </div>
      <div style="line-height:1.7;">
        📈 Clasament & Formă: <b>${m.hForm}</b> vs <b>${m.aForm}</b><br>
        🚩 Cornere: ${cornersDisplay}<br>
        🟨 Cartonașe: ${cardsDisplay}
      </div>
    </div>
  </div>`;
}

function renderAdminView() {
  const rows = usersList.map(u => {
    const badge = u.role === "admin" ? "👑 ADMIN" : (u.role === "vip" ? "⚡ VIP + JOE" : "👁️ DOAR PRONOSTICURI");
    const col = u.role === "admin" ? "var(--neon-gold)" : (u.role === "vip" ? "var(--neon-green)" : "var(--neon-cyan)");
    const expiryText = u.username === 'teodor' ? 'Acces Permanent (Admin)' : (u.expires_at ? `Valabil până la: ${formatExpiryDate(u.expires_at)}` : 'Fără termen setat');
    
    return `<div class="bet-ticket" style="display:flex;justify-content:space-between;align-items:center;">
      <div>
        <div style="font-size:14px;font-weight:800;color:#fff;">👤 ${u.username} <span style="font-size:10px;color:var(--neon-green);">(🔐 Parolă criptată RLS)</span></div>
        <div style="font-size:10px;font-family:'Orbitron',sans-serif;color:${col};margin-top:4px;font-weight:800;">${badge}</div>
        <div style="font-size:10px;color:var(--text-muted);margin-top:3px;">⏳ ${expiryText}</div>
      </div>
      ${u.username !== 'teodor' ? `<button class="t-btn t-loss" style="flex:0;padding:8px 12px;" onclick="removeUser('${u.username}')">🗑️</button>` : ''}
    </div>`;
  }).join("");

  return `<div class="cyber-card" style="border-color:var(--neon-gold);">
    <div style="font-family:'Orbitron',sans-serif;font-size:13px;font-weight:900;color:var(--neon-gold);margin-bottom:12px;">👑 CREARE CONT UTILIZATOR</div>
    <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Nume utilizator (ex: alex)</label>
    <input type="text" id="newUsername" class="cyber-input" placeholder="ex: alex">
    <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Parolă temporară</label>
    <input type="text" id="newPassword" class="cyber-input" placeholder="ex: parola123">
    <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Tip Pachet</label>
    <select id="newRole" class="cyber-input" style="background:#070d19;">
      <option value="standard">👁️ Standard (Vede DOAR Pronosticuri - Fără Joe)</option>
      <option value="vip" selected>⚡ VIP + JOE (Acces Total)</option>
    </select>
    <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Durată / Valabilitate</label>
    <select id="newDuration" class="cyber-input" style="background:#070d19;">
      <option value="trial">Test 2 Zile</option>
      <option value="1_month" selected>1 Lună</option>
      <option value="3_months">3 Luni</option>
      <option value="6_months">6 Luni</option>
      <option value="1_year">1 An</option>
    </select>
    <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Parolă Master Admin</label>
    <input type="password" id="adminSecretInput" class="cyber-input" placeholder="Parola ta secretă de admin">
    <button class="login-btn" onclick="createNewUser()">+ SALVEAZĂ UTILIZATORUL</button>
    <div id="formResultMsg" style="margin-top: 12px; font-size: 12px; text-align: center; font-weight: bold; word-break: break-all;"></div>
  </div>
  <div class="cyber-sec-head"><span>👥 UTILIZATORI ACTIVI (${usersList.length})</span><span>RLS PROTECTED</span></div>
  ${rows}`;
}

function renderProjectView() {
  const net = +(project.bankroll - project.initial_bankroll).toFixed(2);
  const roi = +((net / project.initial_bankroll) * 100).toFixed(1);
  const settled = project.bets.filter(b => b.status === "WIN" || b.status === "LOSS");
  const wins = project.bets.filter(b => b.status === "WIN").length;
  const wr = settled.length ? Math.round((wins / settled.length) * 100) : 0;
  const prog = Math.max(5, Math.min(100, Math.round(((project.bankroll - 500) / (project.target_bankroll - 500)) * 100)));

  const dayAll = cacheByDate[selectedDate] || [];
  let candidates = dayAll.filter(m => m.status === "NS");
  if (!candidates.length) candidates = [...dayAll];
  candidates.sort((a, b) => b.tipsterScore - a.tipsterScore);
  const bestOfDay = candidates[0];

  const quotes = net >= 0 
    ? `"Suntem pe verde, șefu'! Modelul matematic combină Power Rating-ul cluburilor cu clasamentul la zi."`
    : `"Capul sus! Gestionarea riguroasă a mizei ne protejează banca și ne ține în joc pe termen lung."`;

  let joeAutoPickHtml = "";
  if (bestOfDay) {
    const smart = calculateSmartStake(project.bankroll, bestOfDay);
    const potWin = +(smart.stake * bestOfDay.odd).toFixed(2);
    const alreadyIn = project.bets.some(b => String(b.matchId) === String(bestOfDay.id));
    joeAutoPickHtml = `<div class="joe-pick-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-size:10px;font-weight:900;color:var(--neon-green);font-family:'Orbitron',sans-serif;">🎯 ANALIZA SPECIALĂ A LUI JOE (${bestOfDay.date})</span>
        <span style="font-size:10px;color:var(--text-muted);">${bestOfDay.icon} ${bestOfDay.league} · ${bestOfDay.time}</span>
      </div>
      <div style="font-size:15px;font-weight:800;margin-bottom:8px;color:#fff;">${bestOfDay.home} vs ${bestOfDay.away}</div>
      <div class="prediction-panel">
        <div>
          <div class="pred-main" style="color:var(--neon-cyan);">👉 ${bestOfDay.pick} <span style="color:var(--neon-gold);">@${bestOfDay.odd.toFixed(2)}</span></div>
          <div class="pred-sub">Siguranță: <b style="color:var(--neon-green);">${bestOfDay.prob}%</b> · xG: ${bestOfDay.lamH}-${bestOfDay.lamA}<br>Miză recomandată (${smart.pct}%): <b style="color:#fff;">${smart.stake} RON</b> ➔ Câștig: <b style="color:var(--neon-green);">${potWin} RON</b></div>
        </div>
      </div>
      <div class="action-bar" style="margin-top:10px;">
        <button class="cyber-btn copy-btn" onclick="copyMatchById('${bestOfDay.id}')">📋 Copiază Pontul</button>
        <button class="cyber-btn accent" style="font-weight:800;" onclick="addMatchToProject('${bestOfDay.id}')">${alreadyIn ? '✔ În Portofoliu' : '⚡ Adaugă la Joe Vault'}</button>
      </div>
    </div>`;
  }

  const betsHtml = project.bets.map(b => {
    const pot = +(b.stake * b.odd).toFixed(2);
    const col = b.status === "WIN" ? "var(--neon-green)" : (b.status === "LOSS" ? "var(--neon-red)" : "var(--neon-gold)");
    const lbl = b.status === "WIN" ? `✔ WIN (+${(pot-b.stake).toFixed(2)})` : (b.status === "LOSS" ? `✖ LOSS (-${b.stake})` : `⏳ PENDING (${pot})`);
    return `<div class="bet-ticket">
      <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted);font-family:'Orbitron',sans-serif;"><span>${b.date} · ${b.league}</span><span style="font-weight:800;color:${col};">${lbl}</span></div>
      <div style="font-size:14px;font-weight:800;margin:6px 0;">${b.match} ${b.score ? `(${b.score})` : ''}</div>
      <div style="font-size:12px;color:var(--neon-cyan);">Pronostic: <b>${b.pick}</b> | Cotă: <b style="color:var(--neon-gold);">@${b.odd.toFixed(2)}</b> | Miză: <b>${b.stake} RON</b></div>
      <div class="bet-ticket-actions">
        <button class="t-btn t-edit" onclick="editBetDetails(${b.id})">✏️ Cotă</button>
        <button class="t-btn t-win" onclick="updateBetStatus(${b.id},'WIN')">✔ Win</button>
        <button class="t-btn t-loss" onclick="updateBetStatus(${b.id},'LOSS')">✖ Loss</button>
        <button class="t-btn" onclick="deleteBet(${b.id})">🗑️ Șterge</button>
      </div>
    </div>`;
  }).join("");

  return `<div class="vault-hero">
    <div class="vault-profile">
      <div class="joe-avatar-box">
        <img src="IMG_3705.jpeg" alt="Joe" style="width:100%; height:100%; object-fit:cover;">
        <div class="joe-status-dot"></div>
      </div>
      <div>
        <div style="font-family:'Orbitron',sans-serif;font-size:15px;font-weight:900;color:#fff;">Joe's Safe Vault</div>
        <div style="font-size:9px;color:var(--neon-cyan);font-family:'Orbitron',sans-serif;">STATISTICAL STAKING & BANKROLL</div>
      </div>
    </div>
    <div class="vault-quote">${quotes}</div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;padding-top:12px;border-top:1px solid var(--card-border);">
      <div><div class="v-lbl">Capital Activ</div><div style="font-family:'Orbitron',sans-serif;font-size:24px;font-weight:900;">${project.bankroll.toFixed(2)} <span style="font-size:13px;color:var(--neon-green);">RON</span></div></div>
      <div style="text-align:right;"><div class="v-lbl">Țintă</div><div style="font-family:'Orbitron',sans-serif;font-size:14px;font-weight:900;color:var(--neon-gold);">${project.target_bankroll} RON</div></div>
    </div>
    <div class="cyber-progress"><div class="cyber-progress-fill" style="width:${prog}%;"></div></div>
    <div class="vault-kpi-grid">
      <div class="vault-kpi"><div class="v-lbl">Profit Net</div><div class="v-val" style="color:${net>=0?'var(--neon-green)':'var(--neon-red)'};">${net>=0?'+':''}${net}</div></div>
      <div class="vault-kpi"><div class="v-lbl">ROI</div><div class="v-val" style="color:var(--neon-cyan);">${roi>=0?'+':''}${roi}%</div></div>
      <div class="vault-kpi"><div class="v-lbl">Win Rate</div><div class="v-val" style="color:var(--neon-gold);">${wr}%</div></div>
    </div>
  </div>

  <div class="joe-chat-box">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span style="font-family:'Orbitron',sans-serif;font-size:12px;font-weight:900;color:var(--neon-cyan);">💬 CHAT TACTIC VIP CU JOE (VISION AI)</span>
      <span style="font-size:9px;color:var(--neon-green);font-family:'Orbitron',sans-serif;">● ONLINE</span>
    </div>
    <div class="chat-messages" id="chatMessagesBox"></div>
    <form class="chat-form" onsubmit="handleVipChatSubmit(event)">
      <label class="chat-file-btn ${lastUploadedImage ? 'has-img' : ''}" id="chatCamBtn" title="Încarcă poză cu biletul sau statisticile">
        📷 <input type="file" accept="image/*" style="display:none;" onchange="handleImageUpload(event)">
      </label>
      <input type="text" id="vipChatInput" class="cyber-input" style="margin:0;" placeholder="Întreabă-l pe Joe sau încarcă pe 📷...">
      <button type="submit" class="cyber-btn accent" style="flex:0;padding:10px 14px;cursor:pointer;">Trimite</button>
    </form>
  </div>

  ${joeAutoPickHtml}
  <div class="cyber-sec-head" style="margin-top:16px;"><span>📋 PORTOFOLIU JOE (${project.bets.length})</span><span>LIVE DB</span></div>
  ${betsHtml || '<div class="cyber-card" style="text-align:center;color:var(--text-muted);padding:24px;">Portofoliu gol. Adaugă ponturi de la Joe de mai sus!</div>'}`;

  setTimeout(updateChatUI, 50);
}

function computeRealPerformanceStats(dayPool) {
  const settledBets = (project.bets || []).filter(b => b.status === "WIN" || b.status === "LOSS");
  const wonBets = settledBets.filter(b => b.status === "WIN").length;

  const ftMatches = (dayPool || []).filter(m => m.status === "FT" && m.hScore !== null && m.aScore !== null);
  let ftHits = 0;
  ftMatches.forEach(m => {
    if (checkBetOutcome(m.pick, m.hScore, m.aScore, m.hHT, m.aHT) === true) ftHits++;
  });

  let winRateText = "În calcul";
  if (settledBets.length > 0) {
    winRateText = `${Math.round((wonBets / settledBets.length) * 100)}% (${wonBets}/${settledBets.length})`;
  } else if (ftMatches.length > 0) {
    winRateText = `${Math.round((ftHits / ftMatches.length) * 100)}% (${ftHits}/${ftMatches.length} azi)`;
  }

  let avgOddText = "—";
  if ((project.bets || []).length > 0) {
    const sumOdds = project.bets.reduce((acc, b) => acc + (parseFloat(b.odd) || 1.5), 0);
    avgOddText = (sumOdds / project.bets.length).toFixed(2);
  } else if (dayPool && dayPool.length > 0) {
    const sumDayOdds = dayPool.reduce((acc, m) => acc + m.odd, 0);
    avgOddText = (sumDayOdds / dayPool.length).toFixed(2);
  }

  return { winRateText, avgOddText };
}

function renderTicketsView() {
  const dayPool = cacheByDate[selectedDate] || [];
  let pool = dayPool.filter(m => m.status === "NS");
  if (!pool.length) pool = [...dayPool];

  const built = buildOptimalTicket(pool, targetTicketOdds);
  const picks = built.picks;
  const tot = built.totalOdd;

  currentTicketPicks = picks;
  currentTicketTotalOdd = tot;

  const realStats = computeRealPerformanceStats(dayPool);
  const potentialWin = +(customBudget * tot).toFixed(2);
  const btns = [2, 5, 10, 20, 50].map(o => `<button class="cyber-chip cyber-chip-gold ${targetTicketOdds===o?'active':''}" onclick="selectTicketOdd(${o})">Cotă ${o}</button>`).join("");
  
  let contentBody = "";
  if (isGeneratingTicket) {
    contentBody = `<div class="neural-loader-box">
      <div class="neural-loader-title" id="neuralStepText">⚡ Extragere date clasament & xG...</div>
      <div class="neural-scan-bar"><div class="neural-scan-fill"></div></div>
      <div style="font-size:10px;color:var(--text-muted);font-family:'Orbitron',sans-serif;">NEURAL ENGINE · COTA ȚINTĂ ~${targetTicketOdds}</div>
    </div>`;
  } else {
    const rows = picks.map((m, i) => `<div class="ticket-row-item" style="animation-delay:${i * 0.08}s;">
      <div>
        <div style="font-size:13px;font-weight:800;">${i+1}. ${m.home} vs ${m.away}</div>
        <div style="font-size:11px;color:var(--neon-cyan);">👉 ${m.pick} (${m.prob}%)</div>
      </div>
      <div class="odd-chip">@${m.odd.toFixed(2)}</div>
    </div>`).join("");

    contentBody = `<div style="display:flex;justify-content:space-between;padding-bottom:8px;margin-bottom:10px;border-bottom:1px solid var(--card-border);font-family:'Orbitron',sans-serif;font-size:12px;">
      <span>Cotă Totală: <b style="color:var(--neon-green);">@${tot.toFixed(2)}</b></span>
      <span>Câștig Est.: <b style="color:var(--neon-gold);"><span id="potWinLabel">${potentialWin}</span> RON</b></span>
    </div>
    ${rows || '<div style="text-align:center;color:var(--text-muted);padding:16px;">Nu sunt suficiente meciuri în această zi.</div>'}`;
  }

  return `<div class="cyber-card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <span style="font-family:'Orbitron',sans-serif;font-size:13px;font-weight:900;color:var(--neon-gold);">🎟️ Generator Bilet Smart (${selectedDate})</span>
      <button class="cyber-btn copy-btn" style="flex:0.4;padding:6px 10px;" onclick="copyCurrentTicket()">📋 Copiază</button>
    </div>
    
    <div style="background:rgba(2,4,8,0.7);padding:10px;border-radius:12px;border:1px solid var(--card-border);margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;">
      <span style="font-size:11px;font-family:'Orbitron',sans-serif;color:var(--text-muted);">BUGETUL TĂU (RON):</span>
      <input type="number" id="budgetInput" class="cyber-input" style="width:110px;margin:0;padding:6px 10px;text-align:right;font-family:'Orbitron',sans-serif;font-weight:900;color:var(--neon-green);" value="${customBudget}" oninput="customBudget=parseFloat(this.value)||0;const el=document.getElementById('potWinLabel');if(el)el.innerText=+(customBudget*currentTicketTotalOdd).toFixed(2);">
    </div>

    <div class="h-scroll" style="margin-bottom:12px;">${btns}</div>
    ${contentBody}
  </div>

  <div class="cyber-card" style="border-color:var(--neon-cyan);margin-top:14px;">
    <div style="font-family:'Orbitron',sans-serif;font-size:12px;font-weight:900;color:var(--neon-cyan);margin-bottom:8px;">📊 PERFORMANȚĂ REALĂ PORTOFOLIU & MODEL</div>
    <div style="font-size:11px;color:var(--text-muted);line-height:1.5;margin-bottom:10px;">Statistici calculate live din istoricul pariurilor salvate în Joe Vault și rezultatele înregistrate.</div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center;">
      <div style="background:rgba(2,4,8,0.5);padding:8px;border-radius:10px;border:1px solid var(--card-border);"><span class="v-lbl">Win Rate Real</span><div style="font-family:'Orbitron',sans-serif;font-weight:900;color:var(--neon-green);font-size:11px;margin-top:2px;">${realStats.winRateText}</div></div>
      <div style="background:rgba(2,4,8,0.5);padding:8px;border-radius:10px;border:1px solid var(--card-border);"><span class="v-lbl">Medie Cotă</span><div style="font-family:'Orbitron',sans-serif;font-weight:900;color:var(--neon-gold);font-size:12px;margin-top:2px;">${realStats.avgOddText}</div></div>
      <div style="background:rgba(2,4,8,0.5);padding:8px;border-radius:10px;border:1px solid var(--card-border);"><span class="v-lbl">Motor Statistic</span><div style="font-family:'Orbitron',sans-serif;font-weight:900;color:var(--neon-cyan);font-size:10px;margin-top:2px;">POWER + BAYES</div></div>
    </div>
  </div>`;
}

function renderViewport() {
  renderSubBars();
  const vp = document.getElementById("viewport");
  if (currentNav === "admin" && isAdmin()) { vp.innerHTML = renderAdminView(); return; }
  if (currentNav === "proiect" && hasJoeAccess()) { vp.innerHTML = renderProjectView(); return; }
  if (currentNav === "bilete") { vp.innerHTML = renderTicketsView(); return; }
  
  const searchTerm = (document.getElementById("matchSearchInput")?.value || "").toLowerCase().trim();

  let list = currentNav === "europa" ? europaMatches : (cacheByDate[selectedDate] || []).filter(m => selectedLeague === "ALL" || m.league === selectedLeague);
  
  if (searchTerm) {
    list = list.filter(m => m.home.toLowerCase().includes(searchTerm) || m.away.toLowerCase().includes(searchTerm) || m.league.toLowerCase().includes(searchTerm));
  }

  if (!list.length) { 
    vp.innerHTML = `<div class="cyber-card" style="text-align:center;padding:26px;color:var(--text-muted);">Niciun meci găsit conform căutării sau programat în această zi.</div>`; 
    return; 
  }

  const groups = {};
  list.forEach(m => { if (!groups[m.league]) groups[m.league] = { icon: m.icon, items: [] }; groups[m.league].items.push(m); });
  vp.innerHTML = Object.keys(groups).map(lg => `<div class="cyber-sec-head"><span>${groups[lg].icon} ${lg}</span><span>${groups[lg].items.length} meciuri</span></div>${groups[lg].items.map(renderMatchCard).join("")}`).join("");
}

function selectDay(iso) { 
  selectedDate = iso; 
  selectedLeague = "ALL"; 
  const searchInput = document.getElementById("matchSearchInput");
  if(searchInput) searchInput.value = "";
  loadMatchesForDate(iso); 
}

function selectLeague(lg) { 
  selectedLeague = lg; 
  renderViewport(); 
}

async function switchNav(tab) {
  if (tab === "proiect" && !hasJoeAccess()) return;
  if (tab === "admin" && !isAdmin()) return;
  currentNav = tab;
  document.querySelectorAll(".hud-nav-item").forEach(b => b.classList.remove("active"));
  const btn = document.getElementById("nav-" + tab);
  if (btn) btn.classList.add("active");
  if (tab === "admin") await fetchAdminUsersList();
  if (tab === "europa") loadEuropaMatches(); else renderViewport();
}

(async function startApp() {
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
})();
</script>
</body>
</html>
