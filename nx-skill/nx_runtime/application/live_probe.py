import NXOpen

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    print("LIVE PROBE work part = " + (part.Name if part is not None else "None"))
    print("LIVE PROBE bodies = " + str(len(list(part.Bodies)) if part is not None else -1))

if __name__ == "__main__":
    main()
