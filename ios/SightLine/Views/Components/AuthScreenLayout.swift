import SwiftUI

/// Shared layout keeps decorations, scrolling, and reusable card styling in one place.
struct AuthScreenLayout<FormContent: View, FooterContent: View>: View {
    let variant: PaperBackground.Variant
    let form: FormContent
    let footer: FooterContent

    init(variant: PaperBackground.Variant,
         @ViewBuilder form: () -> FormContent,
         @ViewBuilder footer: () -> FooterContent) {
        self.variant = variant
        self.form = form()
        self.footer = footer()
    }

    var body: some View {
        ZStack {
            PaperBackground(variant: variant)
            GeometryReader { geometry in
                let scale = min(geometry.size.width / 402, 1.2)
                ScrollView {
                    VStack(spacing: 0) {
                        LetterTileTitle(text: "SightLine")
                            .frame(maxWidth: 402)
                            .padding(.top, max(0, 50 * scale - geometry.safeAreaInsets.top))

                        form
                            .frame(maxWidth: 327)
                            .background {
                                if variant == .signUp {
                                    Image("SLSignupCard")
                                        .resizable(capInsets: EdgeInsets(top: 16, leading: 16, bottom: 26, trailing: 16))
                                        .padding(.horizontal, -4)
                                        .padding(.bottom, -10)
                                        .accessibilityHidden(true)
                                } else {
                                    RoundedRectangle(cornerRadius: Theme.cardCornerRadius)
                                        .fill(Theme.card)
                                        .shadow(color: .black.opacity(0.25), radius: 2, x: 0, y: 6)
                                }
                            }
                            .overlay(alignment: .topTrailing) {
                                decoration(variant == .logIn ? "SLSmallStarLogin" : "SLSmallStarSignup",
                                           width: 102.884, height: 98.4025, angle: -20,
                                           boundsWidth: 127.934, boundsHeight: 128.041)
                                    .offset(x: 50.934, y: -59)
                            }
                            .overlay(alignment: .topLeading) {
                                if variant == .logIn {
                                    paperClip(width: 91, height: 36, angle: -90,
                                              boundsWidth: 36, boundsHeight: 91)
                                        .offset(x: 15, y: -28)
                                }
                            }
                            .overlay(alignment: .bottomTrailing) {
                                if variant == .signUp {
                                    paperClip(width: 68.033, height: 27.213, angle: 100,
                                              boundsWidth: 38.613, boundsHeight: 71.725)
                                        .offset(x: -39.187, y: 34.175)
                                }
                            }
                            .padding(.horizontal, 20)
                            .padding(.top, 52 * scale)

                        footer
                            .font(Theme.handwriting())
                            .foregroundStyle(Theme.text)
                            .frame(minHeight: 44)
                            .frame(width: 250)
                            .background {
                                RoundedRectangle(cornerRadius: Theme.cardCornerRadius)
                                    .fill(Theme.card)
                                    .shadow(color: .black.opacity(0.25), radius: 2, x: 0, y: 6)
                            }
                            .overlay(alignment: .bottomLeading) {
                                if variant == .logIn {
                                    decoration("SLLinkStarLogin", width: 92.9653, height: 91.3196,
                                               angle: 15, boundsWidth: 110.135, boundsHeight: 112.099)
                                        .offset(x: -45, y: 74.099)
                                }
                            }
                            .overlay(alignment: .bottomTrailing) {
                                if variant == .signUp {
                                    decoration("SLLinkStarSignup", width: 102.146, height: 93.6806,
                                               angle: 15, boundsWidth: 120.135, boundsHeight: 117.119)
                                        .offset(x: 89.135, y: 76.619)
                                } else {
                                    paperClip(width: 68.033, height: 27.213, angle: 100,
                                              boundsWidth: 38.613, boundsHeight: 71.725)
                                        .offset(x: -1.187, y: -9.825)
                                }
                            }
                            .buttonStyle(.plain)
                            .padding(.top, variant == .logIn ? 63 * scale : 46 * scale)

                        Spacer(minLength: 160 * scale)
                    }
                    .frame(maxWidth: .infinity)
                    .frame(minHeight: geometry.size.height, alignment: .top)
                }
                .scrollDismissesKeyboard(.interactively)
            }
        }
        .toolbar(.hidden, for: .navigationBar)
    }

    private func decoration(_ name: String, width: CGFloat, height: CGFloat, angle: Double,
                            boundsWidth: CGFloat, boundsHeight: CGFloat) -> some View {
        Image(name)
            .resizable()
            .scaledToFit()
            .frame(width: width, height: height)
            .rotationEffect(.degrees(angle))
            .frame(width: boundsWidth, height: boundsHeight)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }

    private func paperClip(width: CGFloat, height: CGFloat, angle: Double,
                           boundsWidth: CGFloat, boundsHeight: CGFloat) -> some View {
        Image("SLPaperClip")
            .resizable()
            .scaledToFit()
            .frame(width: width, height: height)
            .rotationEffect(.degrees(angle))
            .frame(width: boundsWidth, height: boundsHeight)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }
}
