# UI/Backend Inconsistency Audit Report
**Scan Date:** January 11, 2026  
**Status:** Complete game-wide scan + user-reported bugs fixed  
**Last Updated:** January 11, 2026 (Commit 191beb0a)

---

## ⚠️ NEWLY DISCOVERED CRITICAL BUGS (User Reported)

### BUG 1: **Power Status Check (production == consumption)** ✅ FIXED
**Location:** `province.py` line 138  
**Issue:** Province shows "unpowered" when production exactly equals consumption  
**User Report:**
```
"I am currently producing 4 units of electricity and consuming 4 units 
of electricity, but it looks like my province is unpowered."
```

**Root Cause:**
```python
# OLD CODE (WRONG):
return production > consumption  # Returns False when 4 == 4

# FIXED CODE:
return production >= consumption  # Returns True when 4 == 4
```

**Status:** ✅ **FIXED** in commit 191beb0a  
**Impact:** Users with balanced energy now correctly show as powered

---

### BUG 2: **Coal Power Plant Consumption Mismatch** ✅ FIXED
**Location:** `variables.py` INFRA vs NEW_INFRA  
**User Report:**
```
"I have two coal mines and get 62 units of coal per hour (31 each).
Coal power plant is supposed to take 48 coal per hour.
But I have a net gain of 51 coal per hour, meaning it only uses 11 coal."
```

**Root Cause:** Backend uses `NEW_INFRA` but UI displays `INFRA` (old values)
- **UI displayed (INFRA line 171):** `"coal_burners_convert_minus": [{"coal": 48}]`
- **Backend uses (NEW_INFRA line 418):** `"minus": {"coal": 11}`
- **User calculation proves backend:** 62 production - 11 consumption = 51 net ✓

**Full INFRA/NEW_INFRA Synchronization (Commit 191beb0a):**

| Building | Stat | OLD INFRA | NEW_INFRA | Fixed |
|----------|------|-----------|-----------|-------|
| coal_burners | coal consumption | 48 | 11 | ✅ |
| coal_burners | pollution | 7% | 6% | ✅ |
| oil_burners | oil consumption | 56 | 16 | ✅ |
| oil_burners | pollution | 5% | 4% | ✅ |
| solar_fields | energy | 4 | 3 | ✅ |
| solar_fields | money | 11000 | 13000 | ✅ |
| malls | pollution | 10% | 9% | ✅ |
| farms | rations | 20 | 12 | ✅ |

**Status:** ✅ **FIXED** - All OLD INFRA values now match NEW_INFRA backend implementation  
**Impact:** UI tooltips now display accurate resource consumption/production

---

## CRITICAL INCONSISTENCIES FOUND (Previous Scan)

### 1. **HAPPINESS MULTIPLIER - Major Discrepancy** ⚠️
**Location:** `templates/province.html` line 167 & 175  
**UI Tooltip Claims:**
```
"Each percent of happiness increases max population by 1.2%"
```

**Backend Formula:** `tasks.py` lines 356-358
```python
happiness_multiplier = (happiness - 50) * variables.DEFAULT_HAPPINESS_GROWTH_MULTIPLIER / 50
# where DEFAULT_HAPPINESS_GROWTH_MULTIPLIER = 0.04
```

**Calculation Analysis:**
- **Actual impact per happiness point:** 0.08% (not 1.2%)
- At 50% happiness: 0% net impact (neutral) ✓
- At 100% happiness: +4% total impact (0.08% × 50 points) = **0.08% per point**
- At 0% happiness: -4% total impact

**Issue:** UI claims 1.2% per point, but implementation is only 0.08% per point  
**Severity:** HIGH - **15× difference in claimed vs actual multiplier**  
**Fix:** Change tooltip to "Each percent of happiness increases max population by 0.08%" (or adjust formula to match UI)

---

### 2. **POLLUTION MULTIPLIER - Major Discrepancy** ⚠️
**Location:** `templates/province.html` line 207  
**UI Tooltip Claims:**
```
"Each percent of pollution decreases max population 0.85%"
```

**Backend Formula:** `tasks.py` lines 363-365
```python
pollution_multiplier = (pollution - 50) * -variables.DEFAULT_POLLUTION_GROWTH_MULTIPLIER / 50
# where DEFAULT_POLLUTION_GROWTH_MULTIPLIER = 0.02
```

**Calculation Analysis:**
- **Actual impact per pollution point:** 0.06% (not 0.85%)
- At 50% pollution: 0% net impact (neutral) ✓
- At 100% pollution: -2% total impact (0.06% × 50 points)
- At 0% pollution: +2% total impact

**Issue:** UI claims 0.85% per point, but implementation is only 0.06% per point  
**Severity:** HIGH - **14× difference in claimed vs actual multiplier**  
**Fix:** Change tooltip to "Each percent of pollution decreases max population by 0.06%" (or adjust formula to match UI)

---

## VERIFIED CORRECT IMPLEMENTATIONS ✓

### 3. **PRODUCTIVITY MULTIPLIER** ✓
**Location:** `templates/province.html` line 184 & 192  
**UI Tooltip:**
```
"Each percent of productivity increases resource output by 0.9%"
```
**Backend Implementation:** `tasks.py` lines 641-644 (FIXED in commit 4d8adfca)
```python
if productivity is not None:
    productivity_multiplier = 1 + ((productivity - 50) * variables.DEFAULT_PRODUCTIVITY_PRODUCTION_MUTLIPLIER)
    # where DEFAULT_PRODUCTIVITY_PRODUCTION_MUTLIPLIER = 0.009 (0.9%)
    plus_amount_multiplier *= productivity_multiplier
```
**Status:** ✅ **CORRECT** - Matches UI exactly

---

### 4. **HOSPITAL UPGRADE (National Health Institution)** ✓
**Location:** `templates/upgrades.html` line 184  
**UI Claim:**
```
"increasing each hospital's happiness increase by 30%"
```
**Backend Implementation:** `tasks.py` line 763-765
```python
if unit == "hospitals":
    if upgrades["nationalhealthinstitution"]:
        eff["happiness"] *= 1.3  # 1.3 = 30% increase
```
**Status:** ✅ **CORRECT** - 1.3× multiplier = 30% increase

---

### 5. **MONORAIL UPGRADE (High Speed Rail)** ✓
**Location:** `templates/upgrades.html` line 220  
**UI Claim:**
```
"increases productivity increase by 20%"
```
**Backend Implementation:** `tasks.py` line 768-770
```python
if unit == "monorails":
    if upgrades["highspeedrail"]:
        eff["productivity"] *= 1.2  # 1.2× multiplier = 20% increase
```
**Status:** ✅ **CORRECT** - 1.2× multiplier = 20% increase

---

### 6. **FARM UPGRADE (Advanced Machinery)** ✓
**Location:** `templates/upgrades.html` line 257  
**UI Claim:**
```
"increases farm output by 50%"
```
**Backend Implementation:** `tasks.py` line 783-784
```python
if unit == "farms":
    if upgrades["advancedmachinery"]:
        plus_amount_multiplier += 0.5  # 0.5 = 50% increase
```
**Status:** ✅ **CORRECT** - 0.5 multiplier addition = 50% increase

---

### 7. **BAUXITE UPGRADE (Stronger Explosives)** ✓
**Location:** `templates/upgrades.html` line 291  
**UI Claim:**
```
"increasing production by 45%"
```
**Backend Implementation:** `tasks.py` line 778-779
```python
if unit == "bauxite_mines" and upgrades["strongerexplosives"]:
    plus_amount_multiplier += 0.45  # 0.45 = 45% increase
```
**Status:** ✅ **CORRECT** - 0.45 multiplier addition = 45% increase

---

### 8. **GOVERNMENT REGULATION UPGRADE** ✓
**Location:** `templates/upgrades.html` line 150  
**UI Claim:**
```
"retail producing 25% less pollution"
```
**Backend Implementation:** `tasks.py` lines 849-854
```python
if (unit_category == "retail"
    and upgrades["governmentregulation"]
    and eff == "pollution"
    and sign == "+"):
    eff_amount *= 0.75  # 0.75 = 25% reduction
```
**Status:** ✅ **CORRECT** - 0.75× multiplier = 25% reduction

---

## SECONDARY CHECKS NEEDED

### 9. **CONSUMER GOODS TAX MULTIPLIER**
**Location:** `templates/province.html` line 200  
**UI Claim:**
```
"When consumer spending is 100%, tax income is increased by 150%"
```
**Backend Location:** `tasks.py` line 209 & `variables.py` line 3
```python
CONSUMER_GOODS_TAX_MULTIPLIER = 1.5
# Applied when max_cg <= consumer_goods
# income *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
```
**Status:** ⚠️ **NEEDS VERIFICATION** - Multiplier is 1.5 (50% increase), not 150% increase. Need to verify if UI text is off by one decimal.

---

### 10. **LAND TAX INCOME BONUS**
**Location:** `templates/province.html` line 222  
**UI Claim:**
```
"increases tax income by 2%"
```
**Backend:** `tasks.py` line 187 & `variables.py` line 10
```python
DEFAULT_LAND_TAX_MULTIPLIER = 0.02
land_multiplier = (land - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER
multiplier = base_multiplier + (base_multiplier * land_multiplier)
```
**Status:** ⚠️ **UNCLEAR** - Need to verify this is correctly labeled as "per land slot" vs cumulative

---

### 11. **ELECTRICITY TAX INCOME IMPACT**
**Location:** `templates/province.html` line 230  
**UI Claim:**
```
"Electricity allows for certain infrastructure to function, and affects tax income"
```
**Backend Status:** VAGUE - "affects tax income" is not specific. Need to find exact percentage/multiplier in code.

---

### 12. **LAND POPULATION BONUS**
**Location:** `templates/province.html` line 222  
**UI Claim:**
```
"increases max population by 120,000"
```
**Backend:** `tasks.py` line 333 & `variables.py` line 18
```python
LAND_MAX_POPULATION_ADDITION = 120000
maxPop += land * variables.LAND_MAX_POPULATION_ADDITION
```
**Status:** ✅ **CORRECT**

---

### 13. **CITY POPULATION BONUS**
**Location:** `templates/province.html` line 214  
**UI Claim:**
```
"increases max population by 750,000"
```
**Backend:** `tasks.py` line 331 & `variables.py` line 17
```python
CITY_MAX_POPULATION_ADDITION = 750000
maxPop += citycount * variables.CITY_MAX_POPULATION_ADDITION
```
**Status:** ✅ **CORRECT**

---

## SUMMARY TABLE

| Feature | UI Claim | Backend Actual | Match | Severity |
|---------|----------|----------------|-------|----------|
| Happiness Multiplier | 1.2% per point | 0.08% per point | ❌ | CRITICAL |
| Pollution Multiplier | 0.85% per point | 0.06% per point | ❌ | CRITICAL |
| Productivity Multiplier | 0.9% per point | 0.9% per point | ✅ | N/A |
| Hospital Upgrade | +30% happiness | ×1.3 | ✅ | N/A |
| Monorail Upgrade | +20% productivity | ×1.2 | ✅ | N/A |
| Farm Upgrade | +50% output | +0.5× | ✅ | N/A |
| Bauxite Upgrade | +45% output | +0.45× | ✅ | N/A |
| Gov Regulation | -25% pollution | ×0.75 | ✅ | N/A |
| Consumer Goods Tax | +150% income | ×1.5 (50%?) | ⚠️ | MEDIUM |
| Land Tax Bonus | +2% per slot | varies | ⚠️ | LOW |

---

## ROOT CAUSE ANALYSIS

**Happiness & Pollution Multipliers:**
The UI tooltips appear to have been written based on an older, more aggressive formula design (1.2% and 0.85% per point). The current backend implementation uses a center-neutral design with much smaller impact (4% max at 100% extreme).

**Most likely scenarios:**
1. **UI was written first** with desired game balance, but backend was implemented with different values
2. **Backend was rebalanced** (possibly to prevent runaway snowballing) but UI tooltips were not updated
3. **Tooltips are placeholders** that were meant to be updated but got overlooked

---

## RECOMMENDATIONS

### IMMEDIATE (Critical)
- [ ] **Fix happiness tooltip:** Change from "1.2%" to "0.08%"
- [ ] **Fix pollution tooltip:** Change from "0.85%" to "0.06%"

### SHORT-TERM (Medium)
- [ ] Verify Consumer Goods tax multiplier claim (1.5× = 50% or should it be 250%?)
- [ ] Clarify electricity impact on tax income with specific percentage

### LONG-TERM (Optional)
- [ ] Consider whether happiness/pollution should have stronger impact (rebalance multipliers to match UI promises)
- [ ] Add logging to verify tooltips match actual values in production

---

## FILES TO UPDATE

If implementing the quick fix (update UI):
- `/Users/dede/AnO/templates/province.html` - Lines 167, 175 (happiness), 207 (pollution)

If implementing the proper fix (update backend):
- `/Users/dede/AnO/variables.py` - Lines 14, 15 (update multipliers to 0.012 happiness, 0.0085 pollution)
- `/Users/dede/AnO/tasks.py` - Lines 357, 364 (update formula if needed)

---

## NEXT ACTIONS

1. **Confirm with product team:** Are these stats working as intended, or should they match the UI claims?
2. **Choose approach:** Fix UI or fix backend calculations?
3. **Implement fix** and verify with user testing
4. **Deploy** with commit message explaining the correction
