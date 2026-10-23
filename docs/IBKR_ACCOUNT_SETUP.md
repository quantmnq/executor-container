# Prepare your IBKR account and a separate Gateway login

English | [简体中文](IBKR_ACCOUNT_SETUP.zh-CN.md) | [Back to setup](SETUP.md#prepare)

Complete this before entering IBKR credentials in `./follow-stack setup`.
Use your own browser and phone; Codex or Claude Code can explain each screen.
Account applications, personal details, agreements and authentication stay with you.
Instructions checked October 22, 2026 (US Pacific); labels can vary by account.

## 1. Open an additional account for Auto Quant

If you do not yet have an IBKR relationship, complete IBKR's initial application
and verification first. Then sign in to **Client Portal** with your primary login.

1. Open **User icon → Settings → Trading → Open an Additional Account**. Some
   Settings layouts show **Open an Additional Account** directly.
2. Complete the linked-account application with your own details. Review the
   account type and agreements yourself; the assistant must not choose answers
   about your finances or experience for you.
   Select **Futures** in the requested products and enter your **actual years of
   futures experience**, trades and knowledge. If you have several years, select
   the matching experience bracket. Approval depends on IBKR's eligibility review;
   do not select invented experience to obtain permission.
3. Wait for IBKR to approve and activate the account. This is the dedicated
   Auto Quant account. If you already have a suitable dedicated account, verify
   it and reuse it rather than creating a duplicate.

A linked account has its own account ID and needs separate funding for live use.
Opening it does not create a second login. Start this installation in **paper**;
opening a live account does not authorize funding, transfers or live trading.
[IBKR's additional-account guide](https://www.ibkrguides.com/clientportal/createnewlinkedaccount.htm).

**Checkpoint:** the intended additional account is approved, or an existing
dedicated account is confirmed. Record completion only, without its ID in chat.

## 2. Create a secondary username for the same account holder

1. In Client Portal, open **User icon → Settings → User & Access Rights → Users →
   “+” Add**. Some layouts call the page **Users & Access Rights**.
2. Create a new username and password privately. Select **Yes** for the question
   asking whether this is a **secondary user for the primary account holder**.
   This login belongs to you; do not add Auto Quant or the assistant as a user.
3. Review access to the dedicated account and complete IBKR's confirmation and
   security enrollment. Verify the login has the required futures permissions
   and market-data access; additional users can incur separate market-data fees.
4. Keep your **primary username for phone/manual trading** and reserve the
   **secondary username for Gateway on OCI**. Keep both credentials private.

IBKR permits one active brokerage session per username. A phone trading login
using Gateway's username can disconnect Gateway. An additional linked account
alone does not solve this: the two sessions need distinct usernames. Approving
an IB Key authentication request on your phone is different from opening a
competing mobile trading session.
[IBKR's secondary-username instructions](https://www.ibkrguides.com/clientportal/uar/addingusernamestoauser.htm)
and [session rules](https://ibkrcampus.com/docs/web-api/authentication/sessions).

**Checkpoint:** the secondary username is usable, security enrollment is complete,
and you know which login is reserved for Gateway. Do not share either username
or password in chat or progress notes.

## 3. Request and verify futures trading permission

During account creation, select **Futures**, including **United States** for
CME MNQ/NQ. For an existing account, open **User icon → Settings → Trading →
Trading Permissions**, then **Request/Edit → Futures**. Complete the required
experience/profile questions and disclosures with accurate answers, then save.
IBKR considers your financial profile and investment objectives as well as
experience; selecting a particular number of years does not guarantee approval.

**Checkpoint:** the dedicated account and Gateway user have the required futures
permission approved. If IBKR declines it or requests more information, pause and
resolve that with IBKR; the assistant must not change experience answers to
make the account qualify.
[IBKR trading-permission instructions](https://www.ibkrguides.com/clientportal/tradingpermissions.htm).

## 4. Complete both market-data forms and subscribe to CME Level 1

**Where: Client Portal → User icon → Settings → Trading Platform → Market Data
Subscriptions.** Use the subscriber/login that supplies data to Gateway; a
subscription on the phone's other username is not proof Gateway has data access.

1. Find **Market Data API Acknowledgement**, click its **gear / Configure** icon,
   read and complete the form, then submit/save. Some layouts call this
   **Market Data API Agreement**. Confirm the acknowledgement is completed;
   IBKR can request annual renewal.
2. Find **Market Data Subscriber Status**, click its **gear / Configure** icon,
   and complete that separate form. For a customer who qualifies under the
   exchange's definitions, select **Non-Professional** in the dropdown and answer
   the questionnaire truthfully. Submit and confirm the saved status. If the
   customer is Professional or eligibility is unclear, use the correct status
   and have IBKR clarify the applicable subscription; do not assume everyone
   qualifies for Non-Professional pricing.
3. Under **Current Subscriptions**, click **gear / Configure**. Open the
   **United States / North America → Level 1 (Top of Book)** choices and select
   **CME Real-Time (L1)** (also labeled **CME Real-Time Non-Professional Level 1**).
   The published Non-Professional price checked for this guide is **USD $1.55
   per month**. Review the actual price, billable account and any additional
   per-user charges displayed by IBKR; the customer accepts the recurring
   subscription and exchange agreements before confirmation.
4. Finish the confirmation screens and return to Current Subscriptions to
   verify CME Real-Time (L1) is active. Confirm both forms were saved too;
   subscribing alone does not complete the API acknowledgement or status form.
5. In **Paper Trading Account** settings below, verify the intended paper login
   can receive this real-time data, including any required sharing configuration.
   After login, use the normal Gateway quote check to verify actual access.

This flow selects the CME Level 1 feed for MNQ/NQ. If the price or eligibility
differs, show the customer the actual offer before purchase. Do not substitute a
Level 2 bundle or treat a delayed quote as real-time readiness.
[IBKR subscription instructions](https://www.ibkrguides.com/clientportal/usersettings/marketdatasubscriptions.htm),
[subscriber-status instructions](https://www.ibkrguides.com/clientportal/usersettings/marketdatasubscriberstatus.htm),
[API acknowledgement requirement](https://ibkrcampus.com/docs/web-api/v1/endpoints/market-data/market-data-availability)
and [current market-data fees](https://www.interactivebrokers.com/en/pricing/market-data-pricing.php).

**Checkpoint:** API acknowledgement completed, truthful subscriber status saved,
CME Level 1 active for the intended Gateway login and recurring fee accepted.
Record only completion/pending flags, without personal questionnaire answers.

## 5. Verify the paper login before running the wizard

IBKR paper credentials and account IDs can differ from live credentials and IDs.
Creating a live secondary username does not prove it can access your paper account.
In your live Client Portal, open **User icon → Settings → Account Configuration →
Paper Trading Account** to verify the paper login
and account assigned to the intended setup. If a separate paper login must be
created or enabled, complete IBKR's process before continuing. Reserve that
paper login for OCI and use a different username for phone trading.
[IBKR's paper-account settings](https://www.ibkrguides.com/clientportal/papertradingaccount.htm).

Confirm that the Gateway login can access the intended **paper** account and
that its futures permissions and market-data access are available. Enter this
verified paper login in the Gateway wizard and its paper account ID in the
executor wizard; a username and account ID are different fields. Never enter live
credentials merely because a paper login has not been set up yet.

If an option is missing, approval is pending, or the username cannot access the
intended account, pause this checkpoint and ask IBKR to resolve it. Do not reuse
a competing phone login, force another session offline or repeatedly restart
Gateway as a workaround.

After Gateway connects and **while the executor is still stopped**, sign in to
mobile trading with the other username. Run `./follow-stack check` again (native kits use `./follow check`): the
Gateway session must remain available and account/quote checks must pass. This
checks the login arrangement without placing orders. Do not mark it verified
from a running process alone. Then return to the [setup guide](SETUP.md).
